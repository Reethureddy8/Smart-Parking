"""Pure logic: plates, pricing, layout."""
import json

import pytest

from smartpark import config, layout, plates, pricing
from smartpark.layout import Det
from smartpark.vision import rank_candidates


# ---------------------------------------------------------------- plates
def test_plate_fit_fixes_lookalikes():
    f = plates.fit("KA O1 AB 1Z34")
    assert f.plate == "KA01AB1234" and f.standard and f.corrections == 2


def test_plate_fit_state_bonus_and_pretty():
    assert plates.pretty("AP39CQ0420") == "AP 39 CQ 0420"
    assert plates.fit("AP39CQ0420").score > plates.fit("QQ39CQ0420").score


def test_plate_bh_series():
    f = plates.fit("22BH1234AA")
    assert f.plate == "22BH1234AA" and plates.pretty(f.plate) == "22 BH 1234 AA"


def test_plate_rejects_junk():
    assert plates.fit("HELLO") is None
    assert plates.fit("") is None


def test_manual_validation():
    assert plates.validate_manual(" ka-01 ab 1234 ") == "KA01AB1234"
    for bad in ("AB", "ABCDEFG"):
        with pytest.raises(ValueError):
            plates.validate_manual(bad)


def test_two_line_plate_is_joined():
    boxes = [
        {"text": "KA01", "conf": 0.9, "x1": 100, "y1": 100, "x2": 200, "y2": 140},
        {"text": "AB1234", "conf": 0.85, "x1": 90, "y1": 150, "x2": 230, "y2": 190},
        {"text": "TOYOTA", "conf": 0.95, "x1": 400, "y1": 20, "x2": 520, "y2": 50},
    ]
    assert rank_candidates(boxes)[0]["plate"] == "KA01AB1234"


# ---------------------------------------------------------------- pricing
T = {"grace_min": 10, "first_hour": 40, "per_hour": 20, "daily_cap": 300}


@pytest.mark.parametrize("minutes,total", [
    (5, 0), (11, 40), (60, 40), (61, 60), (180, 80),
    (23 * 60, 300),        # capped
    (24 * 60, 300),        # one full day
    (24 * 60 + 30, 340),   # a day plus a first hour
])
def test_fare_rules(minutes, total):
    assert pricing.compute_fare(minutes, T)["total"] == total


def test_tariff_validation():
    with pytest.raises(ValueError):
        pricing.normalise_tariff({"grace_min": -1, "first_hour": 1, "per_hour": 1, "daily_cap": 1})


# ---------------------------------------------------------------- layout
def test_bundled_layout_is_complete():
    data = json.loads((config.ASSETS / "layout.json").read_text())
    labels = [s["label"] for s in data["slots"]]
    assert labels == [f"A{i}" for i in range(1, 9)] + [f"B{i}" for i in range(1, 9)]


def test_layout_rows_gaps_and_oversize():
    dets = [Det(x, 0.1, x + 0.09, 0.45, "empty", 0.9) for x in (0.0, 0.1, 0.2, 0.4)]  # gap at 0.3
    dets += [Det(x, 0.5, x + 0.09, 0.85, "car", 0.9) for x in (0.0, 0.2, 0.3, 0.4)]
    dets.append(Det(0.1, 0.12, 0.19, 0.84, "car", 0.8))  # van spanning both rows at x=0.1
    lay = layout.build_layout(dets)
    by = {s["label"]: s for s in lay["slots"]}
    assert len(lay["slots"]) == 10
    assert by["A4"]["inferred"] and by["A4"]["seen"] == "empty"
    assert by["B2"]["seen"] == "car" and by["A2"]["seen"] == "car"


def test_wide_layout_transposes():
    dets = [Det(0.1, y, 0.45, y + 0.09, "empty", 0.9) for y in (0.0, 0.1, 0.2)]
    dets += [Det(0.55, y, 0.9, y + 0.09, "empty", 0.9) for y in (0.0, 0.1, 0.2)]
    lay = layout.build_layout(dets)
    assert lay["orientation"] == "wide" and len(lay["slots"]) == 6


def test_observe_and_route():
    slots = json.loads((config.ASSETS / "layout.json").read_text())["slots"]
    a3 = next(s for s in slots if s["label"] == "A3")
    obs = layout.observe(slots, [Det(a3["x1"], a3["y1"], a3["x2"], a3["y2"], "car", 0.9)])
    assert obs["slots"]["A3"]["state"] == "car" and obs["slots"]["A4"]["state"] == "free"
    ent = layout.default_entrance(slots, "tall")
    near = layout.route(next(s for s in slots if s["label"] == "B1"), ent, "tall", slots)["distance"]
    far = layout.route(next(s for s in slots if s["label"] == "B8"), ent, "tall", slots)["distance"]
    assert near < far
