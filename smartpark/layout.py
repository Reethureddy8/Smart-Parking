"""Lot geometry: turn raw detections into a labelled bay grid, match later
camera frames against it, and route drivers from the entrance to a bay.

All coordinates are normalised to 0..1 of the lot image so the same layout works
for any resolution of the same camera view.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass
class Det:
    x1: float
    y1: float
    x2: float
    y2: float
    cls: str  # "car" | "empty"
    conf: float

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1


def _swap(d: Det) -> Det:
    return Det(d.y1, d.x1, d.y2, d.x2, d.cls, d.conf)


def build_layout(dets: list[Det]) -> dict:
    """Cluster detections into rows of bays.

    Works in a frame where bays are 'tall' (long axis vertical); wide-bay lots are
    transposed in and out. Oversized boxes (a van over two bays) are split across
    every row they cover. Returns {"orientation", "slots": [...]} where each slot
    carries label/row/col/box and the class seen at calibration time.
    """
    dets = [d for d in dets if d.w > 0 and d.h > 0]
    if len(dets) < 2:
        raise ValueError("Need at least two detected bays to build a layout.")
    tall = median(d.h for d in dets) >= median(d.w for d in dets)
    if not tall:
        dets = [_swap(d) for d in dets]

    long_ = median(d.h for d in dets)
    short = median(d.w for d in dets)
    normal = [d for d in dets if d.h <= 1.45 * long_ and d.w >= 0.5 * short]
    oversize = [d for d in dets if d.h > 1.45 * long_ and d.w >= 0.5 * short]
    if not normal:
        raise ValueError("Could not find regular bays in this image.")

    # 1) rows: cluster normal boxes by vertical centre
    normal.sort(key=lambda d: (d.y1 + d.y2) / 2)
    rows: list[list[Det]] = [[normal[0]]]
    for d in normal[1:]:
        prev = rows[-1]
        if (d.y1 + d.y2) / 2 - median((p.y1 + p.y2) / 2 for p in prev) > 0.5 * long_:
            rows.append([d])
        else:
            prev.append(d)

    slots = []
    for r, members in enumerate(rows):
        top = median(m.y1 for m in members)
        bot = median(m.y2 for m in members)
        band = bot - top
        cands = list(members)
        for o in oversize:  # split tall vehicles into the rows they cover
            cover = min(o.y2, bot) - max(o.y1, top)
            if cover >= 0.4 * band:
                cands.append(Det(o.x1, top, o.x2, bot, o.cls, o.conf * 0.95))
        # 2) within a row, sort left->right and drop duplicates
        cands.sort(key=lambda d: -d.conf)
        kept: list[Det] = []
        for c in cands:
            dup = False
            for k in kept:
                ov = min(c.x2, k.x2) - max(c.x1, k.x1)
                if ov > 0.5 * min(c.w, k.w):
                    dup = True
                    if c.cls == "car" and k.cls == "empty" and c.conf > 0.5 * k.conf:
                        k.cls = "car"  # a car straddling a detected empty bay wins
                    break
            if not dup:
                kept.append(c)
        kept.sort(key=lambda d: d.x1)
        kept = _fill_gaps(kept, short)
        for c_idx, k in enumerate(kept):
            slots.append({"row": r, "col": c_idx, "x1": k.x1, "y1": top, "x2": k.x2, "y2": bot,
                          "seen": k.cls, "conf": round(k.conf, 3), "inferred": k.conf == 0})

    if not tall:
        for s in slots:
            s["x1"], s["y1"], s["x2"], s["y2"] = s["y1"], s["x1"], s["y2"], s["x2"]
    for s in slots:
        s["label"] = f"{chr(65 + s['row'])}{s['col'] + 1}"
        for k in ("x1", "y1", "x2", "y2"):
            s[k] = round(min(1.0, max(0.0, s[k])), 4)
    return {"orientation": "tall" if tall else "wide", "slots": slots}


def _fill_gaps(row: list[Det], short: float) -> list[Det]:
    """Bays are evenly pitched; infer ones the detector missed between neighbours."""
    if len(row) < 2:
        return row
    centres = [(d.x1 + d.x2) / 2 for d in row]
    diffs = [b - a for a, b in zip(centres, centres[1:])]
    regular = [d for d in diffs if d < 1.5 * short]
    pitch = median(regular) if regular else short
    width = median(d.w for d in row)
    out = [row[0]]
    for prev, cur, gap in zip(row, row[1:], diffs):
        missing = round(gap / pitch) - 1
        if missing >= 1 and gap > 1.6 * pitch:
            step = gap / (missing + 1)
            pc = (prev.x1 + prev.x2) / 2
            for i in range(1, missing + 1):
                c = pc + step * i
                out.append(Det(c - width / 2, prev.y1, c + width / 2, prev.y2, "empty", 0.0))
        out.append(cur)
    return out


def observe(slots: list[dict], dets: list[Det], cover: float = 0.35) -> dict:
    """Which bays does this camera frame show as taken?

    A bay is 'car' when a vehicle box covers >= `cover` of its area, 'free' when an
    empty-bay detection overlaps it (or nothing does), with a confidence.
    """
    cars = [d for d in dets if d.cls == "car"]
    empties = [d for d in dets if d.cls == "empty"]
    out: dict[str, dict] = {}
    matched_cars: set[int] = set()
    for s in slots:
        area = max(1e-9, (s["x2"] - s["x1"]) * (s["y2"] - s["y1"]))
        best, best_conf = 0.0, 0.0
        for i, c in enumerate(cars):
            iw = min(s["x2"], c.x2) - max(s["x1"], c.x1)
            ih = min(s["y2"], c.y2) - max(s["y1"], c.y1)
            if iw > 0 and ih > 0:
                frac = iw * ih / area
                if frac >= cover:
                    matched_cars.add(i)
                if frac > best:
                    best, best_conf = frac, c.conf
        if best >= cover:
            out[s["label"]] = {"state": "car", "conf": round(best_conf, 3)}
            continue
        e_conf = 0.0
        for e in empties:
            iw = min(s["x2"], e.x2) - max(s["x1"], e.x1)
            ih = min(s["y2"], e.y2) - max(s["y1"], e.y1)
            if iw > 0 and ih > 0 and iw * ih / area > 0.4:
                e_conf = max(e_conf, e.conf)
        out[s["label"]] = {"state": "free", "conf": round(e_conf or 0.5, 3)}
    stray = len(cars) - len(matched_cars)
    return {"slots": out, "stray_cars": stray}


# ---------------------------------------------------------------- routing

def lanes(slots: list[dict], orientation: str) -> list[float]:
    """Driving lanes (cross-axis coordinates) between and around the bay rows."""
    rows: dict[int, tuple[float, float]] = {}
    for s in slots:
        a, b = (s["y1"], s["y2"]) if orientation == "tall" else (s["x1"], s["x2"])
        lo, hi = rows.get(s["row"], (a, b))
        rows[s["row"]] = (min(lo, a), max(hi, b))
    spans = [rows[k] for k in sorted(rows)]
    if not spans:
        return [0.5]
    out = [max(0.0, spans[0][0] - 0.03)]
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        out.append((a1 + b0) / 2)
    out.append(min(1.0, spans[-1][1] + 0.03))
    return out


def default_entrance(slots: list[dict], orientation: str) -> dict:
    ln = lanes(slots, orientation)
    mid = ln[len(ln) // 2] if len(ln) > 2 else ln[0]
    return {"x": 0.0, "y": round(mid, 4)} if orientation == "tall" else {"x": round(mid, 4), "y": 1.0}


def route(slot: dict, entrance: dict, orientation: str, all_slots: list[dict]) -> dict:
    """Manhattan path entrance -> lane -> bay mouth. Returns points + distance."""
    ln = lanes(all_slots, orientation)
    tall = orientation == "tall"
    ex, ey = (entrance["x"], entrance["y"]) if tall else (entrance["y"], entrance["x"])
    # transpose into the 'tall' frame
    sx1, sy1, sx2, sy2 = (slot["x1"], slot["y1"], slot["x2"], slot["y2"]) if tall else \
        (slot["y1"], slot["x1"], slot["y2"], slot["x2"])
    cx = (sx1 + sx2) / 2
    # candidate lanes touching the bay: the closest one above and below
    above = [l for l in ln if l <= sy1 + 1e-6]
    below = [l for l in ln if l >= sy2 - 1e-6]
    options = []
    if above:
        options.append((max(above), sy1))
    if below:
        options.append((min(below), sy2))
    if not options:
        options.append((ey, sy1))

    def cost(opt):
        lane, mouth = opt
        inner = 0 if 0 < lane < 1 and lane not in (ln[0], ln[-1]) else 0.05  # prefer shared aisles
        return abs(ey - lane) + abs(ex - cx) + abs(lane - mouth) + inner

    lane, mouth = min(options, key=cost)
    pts = [(ex, ey), (ex, lane), (cx, lane), (cx, (mouth + (sy1 + sy2) / 2) / 2)]
    if not tall:
        pts = [(y, x) for x, y in pts]
    dist = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(pts, pts[1:]))
    # drop zero-length legs
    clean = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - clean[-1][0]) > 1e-4 or abs(p[1] - clean[-1][1]) > 1e-4:
            clean.append(p)
    return {"points": [[round(x, 4), round(y, 4)] for x, y in clean], "distance": round(dist, 4)}
