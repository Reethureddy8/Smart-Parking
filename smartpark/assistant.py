"""Operator assistant. Answers from live lot data.

With GEMINI_API_KEY set it uses Gemini, grounded in a snapshot of the lot.
Without a key it still answers the common questions from the database.
"""
from __future__ import annotations

import re
import time
from typing import Iterator

from . import config, db, plates, pricing, services


def _fmt_dur(minutes: float) -> str:
    m = int(minutes)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def snapshot() -> str:
    st = services.stats()
    with db.read() as conn:
        s = services.settings(conn)
        lot = services.lot(conn)
    cur = s["currency"]
    now = time.time()
    parked = [x for x in lot["slots"] if x["status"] == "parked"]
    lines = [
        f"Lot: {s['lot_name']}. Capacity {lot['capacity']} bays. Time now {time.strftime('%H:%M')}.",
        f"Free {lot['counts']['free']}, parked with ticket {lot['counts']['parked']}, "
        f"seen by camera without ticket {lot['counts']['untracked']}, closed bays {lot['counts']['closed']}.",
        f"Today: {st['entries_today']} entries, {st['exits_today']} exits, revenue {cur}{st['revenue_today']:g}; "
        f"open tickets would pay {cur}{st['projected']:g} if they left now.",
        "Tariffs: " + "; ".join(
            f"{pricing.VEHICLE_CLASSES[c]}: {t['grace_min']} min free, {cur}{t['first_hour']:g} first hour, "
            f"{cur}{t['per_hour']:g}/extra hour, cap {cur}{t['daily_cap']:g}/day" for c, t in s["tariffs"].items()),
        "Free bays: " + (", ".join(x["label"] + (f" ({x['kind']})" if x["kind"] != "standard" else "")
                                    for x in lot["slots"] if x["status"] == "free") or "none"),
        "Parked vehicles: " + ("; ".join(
            f"{x['ticket']['display']} in {x['label']} for {_fmt_dur((now - x['ticket']['entry_at']) / 60)}"
            for x in parked) or "none"),
        "Alerts: " + ("; ".join(a["text"] for a in st["alerts"]) or "none"),
    ]
    return "\n".join(lines)


SYSTEM = """You are the operations assistant inside SmartPark, a parking management console used by lot staff.
You can see a live snapshot of the lot below. Answer briefly and concretely (1-4 sentences or a short list),
using the numbers in the snapshot. If something isn't in the snapshot, say so instead of guessing.
How the system works: the entry camera reads number plates (EasyOCR) and the operator confirms them; the nearest
suitable free bay is assigned and a route is drawn from the entrance; a lot camera (YOLO model) marks which bays
physically have cars, so staff can spot vehicles without a ticket; at exit the fare is computed from the tariff and
paid by UPI QR, cash or card.

LIVE SNAPSHOT
{snapshot}"""


def stream(messages: list[dict]) -> Iterator[str]:
    msgs = [m for m in messages if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()][-12:]
    if not msgs or msgs[-1]["role"] != "user":
        yield "Ask me something about the lot."
        return
    if config.GEMINI_API_KEY:
        try:
            yield from _gemini(msgs)
            return
        except Exception as exc:  # fall back rather than fail the operator
            yield f"(Gemini unavailable: {type(exc).__name__}. Answering from local data.)\n\n"
    yield offline_answer(msgs[-1]["content"])


def _gemini(msgs: list[dict]) -> Iterator[str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents = [types.Content(role="user" if m["role"] == "user" else "model",
                              parts=[types.Part.from_text(text=str(m["content"])[:2000])]) for m in msgs]
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM.format(snapshot=snapshot()))
    for chunk in client.models.generate_content_stream(model=config.GEMINI_MODEL, contents=contents, config=cfg):
        if chunk.text:
            yield chunk.text


# ------------------------------------------------------------------ offline

def offline_answer(q: str) -> str:
    text = q.lower()
    with db.read() as conn:
        s = services.settings(conn)
        lot = services.lot(conn)
    cur = s["currency"]
    now = time.time()

    # a plate mentioned?
    for tok in re.findall(r"[A-Za-z0-9 ]{4,14}", q):
        f = plates.fit(tok)
        if f and f.standard:
            t = services.find_ticket(f.plate)
            if t:
                return (f"{t['display']} is in bay **{t['slot_label']}** since {time.strftime('%H:%M', time.localtime(t['entry_at']))} "
                        f"({_fmt_dur(t['minutes'])}). Fare if it leaves now: {cur}{t['quote']['total']:g}. Ticket {t['code']}.")
            return f"{plates.pretty(f.plate)} isn't parked here right now."

    m = re.search(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minutes)\b", text)
    if m and any(w in text for w in ("cost", "price", "fare", "charge", "how much", "pay")):
        mins = float(m.group(1)) * (60 if m.group(2).startswith("h") else 1)
        cls = next((c for c in pricing.VEHICLE_CLASSES if c in text or pricing.VEHICLE_CLASSES[c].lower() in text), "car")
        if "bike" in text or "two" in text:
            cls = "bike"
        q2 = pricing.compute_fare(mins, s["tariffs"][cls])
        return f"{_fmt_dur(mins)} for a {pricing.VEHICLE_CLASSES[cls].lower()} costs **{cur}{q2['total']:g}** ({', '.join(q2['lines'])})."

    if any(w in text for w in ("free", "available", "empty", "vacant", "space", "spot", "bay")):
        free = [x for x in lot["slots"] if x["status"] == "free"]
        if not free:
            return "No free bays right now."
        pick = services.preview_assignment("car", False)
        nxt = f" The next car would go to **{pick['label']}**." if pick else ""
        return f"**{len(free)} of {lot['capacity']}** bays are free: {', '.join(x['label'] for x in free[:14])}.{nxt}"

    if any(w in text for w in ("revenue", "earn", "collect", "money", "income", "sales")):
        st = services.stats()
        return (f"Today: **{cur}{st['revenue_today']:g}** from {st['exits_today']} exits. "
                f"Open tickets would add {cur}{st['projected']:g} if they left now.")

    if any(w in text for w in ("rate", "tariff", "price", "cost", "charge", "fee")):
        return "\n".join(f"- **{pricing.VEHICLE_CLASSES[c]}**: {t['grace_min']} min free, {cur}{t['first_hour']:g} first hour, "
                         f"{cur}{t['per_hour']:g} each extra hour, max {cur}{t['daily_cap']:g}/day"
                         for c, t in s["tariffs"].items())

    if any(w in text for w in ("alert", "untracked", "ticket", "camera", "problem", "issue", "wrong")):
        st = services.stats()
        if not st["alerts"]:
            return "No alerts. Every vehicle the camera sees has a ticket."
        return "\n".join(f"- {a['text']}" for a in st["alerts"][:8])

    if any(w in text for w in ("busy", "peak", "busiest", "occupancy", "full")):
        st = services.stats()
        p = st["peak"]
        peak = f" Busiest hour today so far: {p['hour']:02d}:00 with {p['count']} vehicles." if p else ""
        return f"Occupancy is **{st['occupancy']}%** ({lot['counts']['parked']} ticketed, {lot['counts']['untracked']} untracked).{peak}"

    if any(w in text for w in ("parked", "vehicles", "cars", "who", "list", "longest")):
        parked = sorted((x for x in lot["slots"] if x["status"] == "parked"), key=lambda x: x["ticket"]["entry_at"])
        if not parked:
            return "No vehicles are parked with a ticket."
        return "\n".join(f"- {x['ticket']['display']} in {x['label']} · {_fmt_dur((now - x['ticket']['entry_at']) / 60)}"
                         for x in parked[:12])

    return ("I can answer from live lot data. Try:\n- how many bays are free?\n- where is KA01AB1234?\n"
            "- how much for 3 hours?\n- today's revenue\n- any alerts?\n- who's parked longest?"
            + ("" if config.GEMINI_API_KEY else "\n\nSet GEMINI_API_KEY to enable free-form answers."))
