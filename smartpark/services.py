"""Business rules: slot assignment, tickets, fares, camera reconciliation, stats."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

from . import config, db, layout, plates, pricing
from .events import bus
from .vision import vision


class Conflict(Exception):
    def __init__(self, message: str, data: dict | None = None):
        super().__init__(message)
        self.data = data or {}


class NotFound(Exception):
    pass


SLOT_KINDS = ("standard", "ev", "accessible", "large", "bike")
PAY_METHODS = ("upi", "cash", "card", "waived")

# Lower rank = better fit. Missing kind = not allowed for that vehicle.
PREFERENCE = {
    "car":   {"standard": 0, "large": 1, "ev": 2, "accessible": 3},
    "ev":    {"ev": 0, "standard": 1, "large": 2, "accessible": 3},
    "bike":  {"bike": 0, "standard": 1, "large": 2, "ev": 3, "accessible": 4},
    "large": {"large": 0, "standard": 1, "ev": 2, "accessible": 3},
}

DEFAULT_SETTINGS = {
    "lot_name": "SmartPark Central",
    "currency": "₹",
    "upi_id": "",
    "payee_name": "SmartPark",
    "tariffs": pricing.DEFAULT_TARIFFS,
    "orientation": "tall",
    "entrance": None,
    "lot_image": {"src": "asset:lot.jpg", "w": 832, "h": 832},
}


# ------------------------------------------------------------------ settings

def settings(conn) -> dict:
    out = {}
    for k, v in DEFAULT_SETTINGS.items():
        out[k] = db.get_setting(conn, k, v)
    tariffs = dict(pricing.DEFAULT_TARIFFS)
    tariffs.update(out["tariffs"] or {})
    out["tariffs"] = tariffs
    return out


def update_settings(conn, patch: dict, user: dict) -> dict:
    cur = settings(conn)
    if "lot_name" in patch:
        name = str(patch["lot_name"]).strip()[:60]
        if not name:
            raise ValueError("Lot name can't be empty.")
        db.set_setting(conn, "lot_name", name)
    if "currency" in patch:
        db.set_setting(conn, "currency", str(patch["currency"]).strip()[:4] or "₹")
    if "upi_id" in patch:
        upi = str(patch["upi_id"]).strip()[:80]
        if upi and ("@" not in upi or " " in upi):
            raise ValueError("UPI ID looks wrong. It should look like name@bank.")
        db.set_setting(conn, "upi_id", upi)
    if "payee_name" in patch:
        db.set_setting(conn, "payee_name", str(patch["payee_name"]).strip()[:60] or "SmartPark")
    if "tariffs" in patch:
        new = dict(cur["tariffs"])
        for cls, t in (patch["tariffs"] or {}).items():
            if cls not in pricing.VEHICLE_CLASSES:
                raise ValueError(f"Unknown vehicle class {cls}")
            new[cls] = pricing.normalise_tariff(t)
        db.set_setting(conn, "tariffs", new)
    if "entrance" in patch:
        e = patch["entrance"]
        db.set_setting(conn, "entrance", {"x": min(1, max(0, float(e["x"]))), "y": min(1, max(0, float(e["y"])))})
    db.log(conn, "settings", f"{user['name']} updated settings", user_id=user["id"])
    return settings(conn)


# ------------------------------------------------------------------ images

def save_image(data: bytes, prefix: str, max_side: int = 1600) -> tuple[str, np.ndarray]:
    """Decode (rejects non-images), shrink, re-encode as JPEG (drops metadata)."""
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("Image is larger than 12 MB.")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("That file isn't a readable image.")
    h, w = img.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1:
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    name = f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.jpg"
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Could not encode image.")
    (config.IMAGES / name).write_bytes(buf.tobytes())
    return name, img


def resolve_media(src: str) -> Path | None:
    """'asset:lot.jpg' | 'sample:lot-a.jpg' | 'data:<file>' -> safe path."""
    kind, _, name = src.partition(":")
    base = {"asset": config.ASSETS, "sample": config.SAMPLES, "data": config.IMAGES}.get(kind)
    if not base or not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    p = (base / name).resolve()
    return p if p.is_file() and base.resolve() in p.parents else None


def samples() -> list[dict]:
    return [{"name": p.name, "src": f"sample:{p.name}"} for p in sorted(config.SAMPLES.glob("*.jpg"))]


# ------------------------------------------------------------------ layout

def ensure_layout() -> None:
    """First boot: load the bundled layout so the lot works before models load."""
    with db.tx() as conn:
        if conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]:
            return
        f = config.ASSETS / "layout.json"
        if not f.exists():
            return
        data = json.loads(f.read_text())
        _write_layout(conn, data["slots"], data["orientation"], data["lot_image"], keep_cam=False)
        db.log(conn, "layout", f"Loaded bundled layout with {len(data['slots'])} bays")


def _write_layout(conn, slots: list[dict], orientation: str, lot_image: dict, keep_cam: bool) -> None:
    conn.execute("DELETE FROM slots")
    t = db.now()
    for s in slots:
        cam = s.get("seen") if keep_cam else None
        conn.execute(
            "INSERT INTO slots(label,row_idx,col_idx,x1,y1,x2,y2,kind,enabled,cam_state,cam_conf,cam_at) "
            "VALUES (?,?,?,?,?,?,?,?,1,?,?,?)",
            (s["label"], s["row"], s["col"], s["x1"], s["y1"], s["x2"], s["y2"], s.get("kind", "standard"),
             {"car": "car", "empty": "free"}.get(cam, "unknown"), s.get("conf") if cam else None,
             t if cam else None))
    db.set_setting(conn, "orientation", orientation)
    db.set_setting(conn, "lot_image", lot_image)
    db.set_setting(conn, "entrance", layout.default_entrance(slots, orientation))


def calibrate(data: bytes | None, sample: str | None, user: dict) -> dict:
    img, src = _load_image(data, sample, "lot")
    dets = vision.detect_lot(img)
    lay = layout.build_layout(dets)
    h, w = img.shape[:2]
    with db.tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM tickets WHERE status='parked'").fetchone()[0]
        if n:
            raise Conflict(f"{n} vehicle(s) are parked. Close or void their tickets before re-mapping the lot.")
        _write_layout(conn, lay["slots"], lay["orientation"], {"src": src, "w": w, "h": h}, keep_cam=True)
        _record_scan(conn, src, lay["slots"], user)
        db.log(conn, "layout", f"{user['name']} re-mapped the lot: {len(lay['slots'])} bays", user_id=user["id"])
    bus.publish("lot")
    return {"bays": len(lay["slots"]), "orientation": lay["orientation"]}


def _record_scan(conn, src, slots, user):
    cars = sum(1 for s in slots if s.get("seen") == "car")
    conn.execute("INSERT INTO scans(at,image,cars,free,stray,user_id) VALUES (?,?,?,?,?,?)",
                 (db.now(), src, cars, len(slots) - cars, 0, user["id"]))


def _load_image(data: bytes | None, sample: str | None, prefix: str) -> tuple[np.ndarray, str]:
    if sample:
        p = resolve_media(f"sample:{sample}")
        if not p:
            raise NotFound("Sample image not found.")
        img = cv2.imread(str(p))
        return img, f"sample:{p.name}"
    if not data:
        raise ValueError("Provide an image or pick a sample.")
    name, img = save_image(data, prefix)
    return img, f"data:{name}"


def update_slot(slot_id: int, patch: dict, user: dict) -> dict:
    with db.tx() as conn:
        s = db.one(conn.execute("SELECT * FROM slots WHERE id=?", (slot_id,)))
        if not s:
            raise NotFound("Bay not found.")
        if "kind" in patch:
            if patch["kind"] not in SLOT_KINDS:
                raise ValueError("Unknown bay type.")
            conn.execute("UPDATE slots SET kind=? WHERE id=?", (patch["kind"], slot_id))
        if "enabled" in patch:
            en = 1 if patch["enabled"] else 0
            if not en and conn.execute("SELECT 1 FROM tickets WHERE slot_id=? AND status='parked'",
                                       (slot_id,)).fetchone():
                raise Conflict("A vehicle is parked here. Move it before closing the bay.")
            conn.execute("UPDATE slots SET enabled=? WHERE id=?", (en, slot_id))
        db.log(conn, "bay", f"{user['name']} updated bay {s['label']}", user_id=user["id"])
    bus.publish("lot")
    return {"ok": True}


# ------------------------------------------------------------------ lot state

def _slot_rows(conn) -> list[dict]:
    return db.rows(conn.execute(
        "SELECT s.*, t.id AS ticket_id, t.plate, t.vehicle_class, t.entry_at, t.code "
        "FROM slots s LEFT JOIN tickets t ON t.slot_id = s.id AND t.status = 'parked' "
        "ORDER BY s.row_idx, s.col_idx"))


def _status(s: dict, now: int) -> str:
    if s["ticket_id"]:
        return "parked"
    if not s["enabled"]:
        return "closed"
    fresh = s["cam_at"] and now - s["cam_at"] < config.CAMERA_STALE_SECONDS
    if fresh and s["cam_state"] == "car":
        return "untracked"
    return "free"


def lot(conn) -> dict:
    st = settings(conn)
    now = db.now()
    slots = _slot_rows(conn)
    out = []
    for s in slots:
        status = _status(s, now)
        fresh = bool(s["cam_at"] and now - s["cam_at"] < config.CAMERA_STALE_SECONDS)
        ghost = status == "parked" and fresh and s["cam_state"] == "free" and s["cam_at"] > (s["entry_at"] or 0)
        out.append({
            "id": s["id"], "label": s["label"], "row": s["row_idx"], "col": s["col_idx"],
            "box": [s["x1"], s["y1"], s["x2"], s["y2"]], "kind": s["kind"], "enabled": bool(s["enabled"]),
            "status": status, "camera": s["cam_state"] if fresh else "unknown", "ghost": ghost,
            "ticket": {"id": s["ticket_id"], "plate": s["plate"], "display": plates.pretty(s["plate"]),
                       "vehicle_class": s["vehicle_class"], "entry_at": s["entry_at"], "code": s["code"]}
            if s["ticket_id"] else None,
        })
    entrance = st["entrance"] or layout.default_entrance(
        [{"row": s["row"], "x1": s["box"][0], "y1": s["box"][1], "x2": s["box"][2], "y2": s["box"][3]}
         for s in out], st["orientation"]) if out else {"x": 0, "y": 0.5}
    last_scan = db.one(conn.execute("SELECT * FROM scans ORDER BY at DESC LIMIT 1"))
    counts = {k: sum(1 for s in out if s["status"] == k) for k in ("free", "parked", "untracked", "closed")}
    return {"slots": out, "counts": counts, "capacity": sum(1 for s in out if s["enabled"]),
            "entrance": entrance, "orientation": st["orientation"], "lot_image": st["lot_image"],
            "last_scan": last_scan, "lot_name": st["lot_name"]}


def _geo(s: dict) -> dict:
    return {"row": s["row_idx"], "x1": s["x1"], "y1": s["y1"], "x2": s["x2"], "y2": s["y2"]}


def pick_slot(conn, vehicle_class: str, accessible: bool) -> dict | None:
    st = settings(conn)
    now = db.now()
    slots = _slot_rows(conn)
    geos = [_geo(s) for s in slots]
    entrance = st["entrance"] or layout.default_entrance(geos, st["orientation"])
    pref = PREFERENCE[vehicle_class]
    best, best_key = None, None
    for s in slots:
        if _status(s, now) != "free" or s["kind"] not in pref:
            continue
        rank = pref[s["kind"]]
        if accessible:
            rank = 0 if s["kind"] == "accessible" else rank + 1
        elif s["kind"] == "accessible":
            rank += 2
        dist = layout.route(_geo(s), entrance, st["orientation"], geos)["distance"]
        key = (rank, dist)
        if best_key is None or key < best_key:
            best, best_key = s, key
    return best


def slot_route(conn, slot_id: int) -> dict | None:
    st = settings(conn)
    slots = db.rows(conn.execute("SELECT * FROM slots"))
    geos = [_geo(s) for s in slots]
    target = next((s for s in slots if s["id"] == slot_id), None)
    if not target:
        return None
    entrance = st["entrance"] or layout.default_entrance(geos, st["orientation"])
    return layout.route(_geo(target), entrance, st["orientation"], geos)


# ------------------------------------------------------------------ tickets

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_code(conn) -> str:
    while True:
        code = "SP-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))
        if not conn.execute("SELECT 1 FROM tickets WHERE code=?", (code,)).fetchone():
            return code


def preview_assignment(vehicle_class: str, accessible: bool, slot_id: int | None = None) -> dict | None:
    with db.read() as conn:
        if slot_id is not None:
            s = db.one(conn.execute("SELECT * FROM slots WHERE id=?", (slot_id,)))
        else:
            s = pick_slot(conn, vehicle_class, accessible)
        if not s:
            return None
        return {"slot_id": s["id"], "label": s["label"], "kind": s["kind"], "route": slot_route(conn, s["id"])}


def create_ticket(plate: str, vehicle_class: str, accessible: bool, slot_id: int | None,
                  image: str | None, ocr_conf: float | None, notes: str | None, user: dict) -> dict:
    plate = plates.validate_manual(plate)
    if vehicle_class not in pricing.VEHICLE_CLASSES:
        raise ValueError("Unknown vehicle type.")
    if image and not resolve_media(f"data:{image}"):
        image = None
    with db.tx() as conn:
        dup = db.one(conn.execute("SELECT id, code, slot_label, entry_at FROM tickets WHERE plate=? AND status='parked'",
                                  (plate,)))
        if dup:
            raise Conflict(f"{plates.pretty(plate)} is already parked in {dup['slot_label']}.", {"ticket_id": dup["id"]})
        if slot_id is not None:
            s = next((r for r in _slot_rows(conn) if r["id"] == slot_id), None)
            if not s:
                raise NotFound("Bay not found.")
            if _status(s, db.now()) not in ("free", "untracked"):
                raise Conflict(f"Bay {s['label']} isn't available.")
        else:
            s = pick_slot(conn, vehicle_class, accessible)
            if not s:
                raise Conflict("The lot is full for this vehicle type.")
        code = _new_code(conn)
        cur = conn.execute(
            "INSERT INTO tickets(code,plate,vehicle_class,slot_id,slot_label,status,entry_at,entry_image,ocr_conf,"
            "accessible,notes,created_by) VALUES (?,?,?,?,?,'parked',?,?,?,?,?,?)",
            (code, plate, vehicle_class, s["id"], s["label"], db.now(), image, ocr_conf,
             1 if accessible else 0, (notes or "").strip()[:200] or None, user["id"]))
        tid = cur.lastrowid
        db.log(conn, "entry", f"{plates.pretty(plate)} parked in {s['label']}", tid, user["id"])
    bus.publish("lot")
    return ticket_detail(tid)


def ticket_detail(tid: int) -> dict:
    with db.read() as conn:
        t = db.one(conn.execute(
            "SELECT t.*, cu.name AS created_by_name, cl.name AS closed_by_name FROM tickets t "
            "LEFT JOIN users cu ON cu.id=t.created_by LEFT JOIN users cl ON cl.id=t.closed_by WHERE t.id=?", (tid,)))
        if not t:
            raise NotFound("Ticket not found.")
        st = settings(conn)
        t["display"] = plates.pretty(t["plate"])
        t["class_name"] = pricing.VEHICLE_CLASSES.get(t["vehicle_class"], t["vehicle_class"])
        end = t["exit_at"] or db.now()
        t["minutes"] = round((end - t["entry_at"]) / 60, 1)
        t["tariff"] = st["tariffs"][t["vehicle_class"]]
        t["quote"] = pricing.compute_fare(t["minutes"], t["tariff"]) if t["status"] == "parked" else None
        t["route"] = slot_route(conn, t["slot_id"]) if t["slot_id"] and t["status"] == "parked" else None
        t["currency"] = st["currency"]
        t["upi_ready"] = bool(st["upi_id"])
        return t


def find_ticket(q: str) -> dict | None:
    q = (q or "").strip()
    if not q:
        return None
    p = plates.clean(q)
    with db.read() as conn:
        r = conn.execute("SELECT id FROM tickets WHERE status='parked' AND (code=? OR plate=?) "
                         "ORDER BY entry_at DESC LIMIT 1", (q.upper(), p)).fetchone()
        if not r and len(p) >= 3:  # partial plate, e.g. last 4 digits
            r = conn.execute("SELECT id FROM tickets WHERE status='parked' AND plate LIKE ? "
                             "ORDER BY entry_at DESC LIMIT 1", (f"%{p}%",)).fetchone()
    return ticket_detail(r["id"]) if r else None


def close_ticket(tid: int, method: str, user: dict) -> dict:
    if method not in PAY_METHODS:
        raise ValueError("Unknown payment method.")
    if method == "waived" and user["role"] != "admin":
        raise PermissionError("Only an admin can waive a fare.")
    with db.tx() as conn:
        t = db.one(conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)))
        if not t:
            raise NotFound("Ticket not found.")
        if t["status"] != "parked":
            raise Conflict("This ticket is already closed.")
        st = settings(conn)
        now = db.now()
        fare = pricing.compute_fare((now - t["entry_at"]) / 60, st["tariffs"][t["vehicle_class"]])["total"]
        if method == "waived":
            fare = 0.0
        conn.execute("UPDATE tickets SET status='closed', exit_at=?, fare=?, pay_method=?, closed_by=? WHERE id=?",
                     (now, fare, method, user["id"], tid))
        db.log(conn, "exit", f"{plates.pretty(t['plate'])} left {t['slot_label']} · {st['currency']}{fare:g} {method}",
               tid, user["id"])
    bus.publish("lot")
    return ticket_detail(tid)


def void_ticket(tid: int, reason: str, user: dict) -> dict:
    if user["role"] != "admin":
        raise PermissionError("Only an admin can void tickets.")
    with db.tx() as conn:
        t = db.one(conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)))
        if not t:
            raise NotFound("Ticket not found.")
        if t["status"] != "parked":
            raise Conflict("Only open tickets can be voided.")
        conn.execute("UPDATE tickets SET status='void', exit_at=?, fare=0, closed_by=?, notes=? WHERE id=?",
                     (db.now(), user["id"], (reason or "voided")[:200], tid))
        db.log(conn, "void", f"{user['name']} voided ticket for {plates.pretty(t['plate'])}", tid, user["id"])
    bus.publish("lot")
    return ticket_detail(tid)


def move_ticket(tid: int, slot_id: int, user: dict) -> dict:
    with db.tx() as conn:
        t = db.one(conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)))
        if not t or t["status"] != "parked":
            raise NotFound("Open ticket not found.")
        s = next((r for r in _slot_rows(conn) if r["id"] == slot_id), None)
        if not s:
            raise NotFound("Bay not found.")
        if _status(s, db.now()) not in ("free", "untracked"):
            raise Conflict(f"Bay {s['label']} isn't available.")
        conn.execute("UPDATE tickets SET slot_id=?, slot_label=? WHERE id=?", (slot_id, s["label"], tid))
        db.log(conn, "move", f"{plates.pretty(t['plate'])} moved {t['slot_label']} → {s['label']}", tid, user["id"])
    bus.publish("lot")
    return ticket_detail(tid)


def list_tickets(status: str | None, q: str | None, frm: int | None, to: int | None,
                 limit: int = 50, offset: int = 0) -> dict:
    where, args = [], []
    if status in ("parked", "closed", "void"):
        where.append("status=?"); args.append(status)
    elif status == "history":
        where.append("status IN ('closed','void')")
    if q:
        where.append("(plate LIKE ? OR code LIKE ? OR slot_label = ?)")
        p = plates.clean(q)
        args += [f"%{p}%", f"%{q.strip().upper()}%", q.strip().upper()]
    if frm:
        where.append("entry_at >= ?"); args.append(int(frm))
    if to:
        where.append("entry_at < ?"); args.append(int(to))
    w = ("WHERE " + " AND ".join(where)) if where else ""
    with db.read() as conn:
        total, revenue = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(fare),0) FROM tickets {w}", args).fetchone()
        items = db.rows(conn.execute(
            f"SELECT id, code, plate, vehicle_class, slot_label, status, entry_at, exit_at, fare, pay_method "
            f"FROM tickets {w} ORDER BY COALESCE(exit_at, entry_at) DESC LIMIT ? OFFSET ?",
            args + [max(1, min(500, limit)), max(0, offset)]))
        st = settings(conn)
    now = db.now()
    for it in items:
        it["display"] = plates.pretty(it["plate"])
        if it["status"] == "parked":
            it["fare_now"] = pricing.compute_fare((now - it["entry_at"]) / 60, st["tariffs"][it["vehicle_class"]])["total"]
    return {"items": items, "total": total, "revenue": round(revenue, 2), "currency": st["currency"]}


# ------------------------------------------------------------------ camera

def scan(data: bytes | None, sample: str | None, user: dict) -> dict:
    img, src = _load_image(data, sample, "scan")
    dets = vision.detect_lot(img)
    with db.tx() as conn:
        slots = db.rows(conn.execute("SELECT * FROM slots"))
        if not slots:
            raise Conflict("Map the lot first.")
        geo = [{"label": s["label"], "x1": s["x1"], "y1": s["y1"], "x2": s["x2"], "y2": s["y2"]} for s in slots]
        obs = layout.observe(geo, dets)
        now = db.now()
        for s in slots:
            o = obs["slots"][s["label"]]
            conn.execute("UPDATE slots SET cam_state=?, cam_conf=?, cam_at=? WHERE id=?",
                         (o["state"], o["conf"], now, s["id"]))
        cars = sum(1 for o in obs["slots"].values() if o["state"] == "car")
        conn.execute("INSERT INTO scans(at,image,cars,free,stray,user_id) VALUES (?,?,?,?,?,?)",
                     (now, src, cars, len(slots) - cars, obs["stray_cars"], user["id"]))
        st = lot(conn)
        db.log(conn, "scan", f"Camera scan: {cars} bays occupied, {st['counts']['untracked']} without a ticket",
               user_id=user["id"])
    bus.publish("lot")
    return {"image": src, "cars": cars, "free": len(slots) - cars, "stray": obs["stray_cars"],
            "untracked": [s["label"] for s in st["slots"] if s["status"] == "untracked"],
            "ghosts": [s["label"] for s in st["slots"] if s["ghost"]],
            "detections": [{"box": [d.x1, d.y1, d.x2, d.y2], "cls": d.cls, "conf": round(d.conf, 2)} for d in dets]}


def clear_camera(user: dict) -> None:
    with db.tx() as conn:
        conn.execute("UPDATE slots SET cam_state='unknown', cam_conf=NULL, cam_at=NULL")
        db.log(conn, "scan", f"{user['name']} cleared camera observations", user_id=user["id"])
    bus.publish("lot")


# ------------------------------------------------------------------ stats

def _local_midnight(ts: float) -> int:
    lt = time.localtime(ts)
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))


def stats() -> dict:
    now = db.now()
    today = _local_midnight(now)
    with db.read() as conn:
        st = settings(conn)
        lot_state = lot(conn)
        tickets = db.rows(conn.execute(
            "SELECT entry_at, exit_at, fare, status, vehicle_class FROM tickets "
            "WHERE status != 'void' AND (exit_at IS NULL OR exit_at >= ?)", (today - 6 * 86400,)))
        activity = db.rows(conn.execute(
            "SELECT a.at, a.kind, a.message, a.ticket_id, u.name AS user FROM activity a "
            "LEFT JOIN users u ON u.id=a.user_id ORDER BY a.at DESC, a.id DESC LIMIT 14"))
    closed_today = [t for t in tickets if t["status"] == "closed" and t["exit_at"] >= today]
    revenue_today = round(sum(t["fare"] or 0 for t in closed_today), 2)
    entries_today = sum(1 for t in tickets if t["entry_at"] >= today)
    week_closed = [t for t in tickets if t["status"] == "closed"]
    avg_stay = round(sum((t["exit_at"] - t["entry_at"]) / 60 for t in week_closed) / len(week_closed)) \
        if week_closed else None

    hours = []
    cur_hour = int((now - today) // 3600)
    for h in range(0, cur_hour + 1):
        a, b = today + h * 3600, min(now, today + (h + 1) * 3600)
        n = sum(1 for t in tickets if t["entry_at"] < b and (t["exit_at"] is None or t["exit_at"] > a))
        hours.append({"hour": h, "count": n})

    days = []
    for d in range(6, -1, -1):
        start = _local_midnight(now - d * 86400)
        end = start + 86400
        rev = sum(t["fare"] or 0 for t in tickets if t["status"] == "closed" and start <= t["exit_at"] < end)
        n = sum(1 for t in tickets if t["status"] == "closed" and start <= t["exit_at"] < end)
        days.append({"start": start, "revenue": round(rev, 2), "sessions": n})

    parked = [s for s in lot_state["slots"] if s["status"] == "parked"]
    long_stays = [s for s in parked if now - s["ticket"]["entry_at"] > 86400]
    projected = 0.0
    for s in parked:
        projected += pricing.compute_fare((now - s["ticket"]["entry_at"]) / 60,
                                          st["tariffs"][s["ticket"]["vehicle_class"]])["total"]
    peak = max(hours, key=lambda h: h["count"]) if hours and any(h["count"] for h in hours) else None

    alerts = []
    for s in lot_state["slots"]:
        if s["status"] == "untracked":
            alerts.append({"level": "warn", "slot": s["label"], "slot_id": s["id"],
                           "text": f"Camera sees a vehicle in {s['label']} with no ticket"})
        if s["ghost"]:
            alerts.append({"level": "warn", "slot": s["label"], "slot_id": s["id"],
                           "text": f"{s['ticket']['display']} has a ticket for {s['label']} but the camera shows it empty"})
    for s in long_stays:
        alerts.append({"level": "info", "slot": s["label"], "slot_id": s["id"],
                       "text": f"{s['ticket']['display']} has been parked over 24 hours"})
    v = vision.status()
    if v["state"] == "error":
        alerts.append({"level": "error", "text": f"Vision models failed to load: {v['detail']}"})

    cap = lot_state["capacity"] or 1
    return {
        "counts": lot_state["counts"], "capacity": lot_state["capacity"],
        "occupancy": round(100 * (lot_state["counts"]["parked"] + lot_state["counts"]["untracked"]) / cap),
        "revenue_today": revenue_today, "entries_today": entries_today, "exits_today": len(closed_today),
        "avg_stay_min": avg_stay, "projected": round(projected, 2), "currency": st["currency"],
        "hours": hours, "days": days, "peak": peak, "alerts": alerts, "activity": activity,
        "mix": {c: sum(1 for s in parked if s["ticket"]["vehicle_class"] == c) for c in pricing.VEHICLE_CLASSES},
    }
