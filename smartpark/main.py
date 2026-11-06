"""HTTP API + static web app."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from . import __version__, assistant, config, db, plates, pricing, security, services
from .events import bus
from .vision import vision

log = logging.getLogger("smartpark")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    services.ensure_layout()
    bus.bind(asyncio.get_running_loop())
    vision.start()
    asyncio.create_task(_vision_watch())
    yield


async def _vision_watch():
    last = None
    while True:
        s = vision.state
        if s != last:
            bus.publish("vision", state=s)
            last = s
        if s in ("ready", "error", "disabled"):
            return
        await asyncio.sleep(1)


app = FastAPI(title="SmartPark", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)


# ------------------------------------------------------------------ middleware

@app.middleware("http")
async def guard(request: Request, call_next):
    # CSRF: state-changing API calls must carry a custom header, which browsers
    # refuse to send cross-site without a CORS preflight we never grant.
    if request.url.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("x-smartpark") != "1":
            return JSONResponse({"error": "Missing request header."}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    return resp


def _err(status: int, msg: str, **data):
    return JSONResponse({"error": msg, **data}, status_code=status)


@app.exception_handler(services.Conflict)
async def _conflict(_, exc: services.Conflict):
    return _err(409, str(exc), **exc.data)


@app.exception_handler(services.NotFound)
async def _nf(_, exc):
    return _err(404, str(exc))


@app.exception_handler(ValueError)
async def _bad(_, exc):
    return _err(400, str(exc))


@app.exception_handler(PermissionError)
async def _perm(_, exc):
    return _err(403, str(exc))


@app.exception_handler(RuntimeError)
async def _rt(_, exc):
    return _err(503, str(exc))


# ------------------------------------------------------------------ auth deps

def current_user(request: Request) -> dict:
    with db.read() as conn:
        u = security.user_for_token(conn, request.cookies.get(config.SESSION_COOKIE))
    if not u:
        raise HTTPException(401, "Please sign in.")
    return u


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admins only.")
    return user


@app.exception_handler(HTTPException)
async def _http(_, exc: HTTPException):
    return _err(exc.status_code, str(exc.detail))


def _set_cookie(resp: Response, token: str, request: Request) -> None:
    resp.set_cookie(config.SESSION_COOKIE, token, max_age=config.SESSION_DAYS * 86400, httponly=True,
                    samesite="strict", secure=request.url.scheme == "https", path="/")


# ------------------------------------------------------------------ meta

@app.get("/api/health")
def health():
    with db.read() as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {"version": __version__, "vision": vision.status(), "ai": bool(config.GEMINI_API_KEY),
            "setup_needed": users == 0}


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class SetupBody(Credentials):
    name: str = Field(min_length=1, max_length=60)
    lot_name: str | None = Field(default=None, max_length=60)


@app.post("/api/setup")
def setup(body: SetupBody, request: Request):
    security.check_password_rules(body.password)
    uname = body.username.strip().lower()
    if not uname.replace("_", "").replace(".", "").isalnum():
        raise ValueError("Username can use letters, numbers, dots and underscores.")
    with db.tx() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise services.Conflict("Setup is already complete.")
        cur = conn.execute("INSERT INTO users(username,name,pw_hash,role,created_at) VALUES (?,?,?,'admin',?)",
                           (uname, body.name.strip(), security.hash_password(body.password), db.now()))
        if body.lot_name and body.lot_name.strip():
            db.set_setting(conn, "lot_name", body.lot_name.strip())
        token = security.create_session(conn, cur.lastrowid)
        db.log(conn, "user", f"{body.name.strip()} set up SmartPark", user_id=cur.lastrowid)
    resp = JSONResponse({"ok": True})
    _set_cookie(resp, token, request)
    return resp


@app.post("/api/login")
def login(body: Credentials, request: Request):
    key = f"{body.username.lower()}|{request.client.host if request.client else ''}"
    wait = security.throttle.retry_after(key)
    if wait:
        return _err(429, f"Too many attempts. Try again in {wait}s.")
    with db.tx() as conn:
        u = db.one(conn.execute("SELECT * FROM users WHERE username=? AND active=1", (body.username.strip(),)))
        if not u or not security.verify_password(body.password, u["pw_hash"]):
            security.throttle.fail(key)
            return _err(401, "Wrong username or password.")
        token = security.create_session(conn, u["id"])
    security.throttle.clear(key)
    resp = JSONResponse({"ok": True})
    _set_cookie(resp, token, request)
    return resp


@app.post("/api/logout")
def logout(request: Request):
    with db.tx() as conn:
        security.drop_session(conn, request.cookies.get(config.SESSION_COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(config.SESSION_COOKIE, path="/")
    return resp


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    with db.read() as conn:
        st = services.settings(conn)
    return {"user": user, "settings": st, "classes": pricing.VEHICLE_CLASSES, "slot_kinds": services.SLOT_KINDS,
            "samples": services.samples()}


# ------------------------------------------------------------------ live

@app.get("/api/lot")
def get_lot(user: dict = Depends(current_user)):
    with db.read() as conn:
        return services.lot(conn)


@app.get("/api/stats")
def get_stats(user: dict = Depends(current_user)):
    return services.stats()


@app.get("/api/stream")
async def stream(request: Request, user: dict = Depends(current_user)):
    q = bus.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ entry

async def _read_upload(f: UploadFile | None) -> bytes | None:
    if f is None:
        return None
    data = await f.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("Image is larger than 12 MB.")
    return data or None


@app.post("/api/plate/read")
async def read_plate(image: UploadFile = File(...), user: dict = Depends(current_user)):
    data = await _read_upload(image)
    if not data:
        raise ValueError("No image received.")
    name, img = await run_in_threadpool(services.save_image, data, "entry")
    t0 = time.time()
    result = await run_in_threadpool(vision.read_plate, img)
    result["image"] = name
    result["ms"] = int((time.time() - t0) * 1000)
    with db.read() as conn:
        for c in result["candidates"]:
            r = conn.execute("SELECT id, slot_label FROM tickets WHERE plate=? AND status='parked'",
                             (c["plate"],)).fetchone()
            c["parked"] = {"ticket_id": r["id"], "slot": r["slot_label"]} if r else None
    return result


@app.get("/api/assign/preview")
def assign_preview(vehicle_class: str = "car", accessible: bool = False, slot_id: int | None = None,
                   user: dict = Depends(current_user)):
    if vehicle_class not in pricing.VEHICLE_CLASSES:
        raise ValueError("Unknown vehicle type.")
    return {"slot": services.preview_assignment(vehicle_class, accessible, slot_id)}


class TicketBody(BaseModel):
    plate: str = Field(max_length=20)
    vehicle_class: str = "car"
    accessible: bool = False
    slot_id: int | None = None
    image: str | None = Field(default=None, max_length=120)
    ocr_conf: float | None = None
    notes: str | None = Field(default=None, max_length=200)


@app.post("/api/tickets")
def create_ticket(body: TicketBody, user: dict = Depends(current_user)):
    return services.create_ticket(body.plate, body.vehicle_class, body.accessible, body.slot_id, body.image,
                                  body.ocr_conf, body.notes, user)


@app.get("/api/tickets")
def list_tickets(status: str | None = None, q: str | None = None, frm: int | None = None, to: int | None = None,
                 limit: int = 50, offset: int = 0, user: dict = Depends(current_user)):
    return services.list_tickets(status, q, frm, to, limit, offset)


@app.get("/api/tickets/export.csv")
def export_csv(status: str | None = "history", q: str | None = None, frm: int | None = None, to: int | None = None,
               user: dict = Depends(current_user)):
    data = services.list_tickets(status, q, frm, to, limit=500)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ticket", "plate", "vehicle", "bay", "status", "entry", "exit", "minutes", "fare", "payment"])
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else ""
    for t in data["items"]:
        mins = round(((t["exit_at"] or time.time()) - t["entry_at"]) / 60)
        w.writerow([t["code"], t["display"], pricing.VEHICLE_CLASSES.get(t["vehicle_class"]), t["slot_label"],
                    t["status"], fmt(t["entry_at"]), fmt(t["exit_at"]), mins, t["fare"] if t["fare"] is not None else "",
                    t["pay_method"] or ""])
    return Response("﻿" + out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="smartpark-{time.strftime("%Y%m%d")}.csv"'})


@app.get("/api/tickets/find")
def find(q: str, user: dict = Depends(current_user)):
    return {"ticket": services.find_ticket(q)}


@app.get("/api/tickets/{tid}")
def ticket(tid: int, user: dict = Depends(current_user)):
    return services.ticket_detail(tid)


class CloseBody(BaseModel):
    method: str


@app.post("/api/tickets/{tid}/close")
def close(tid: int, body: CloseBody, user: dict = Depends(current_user)):
    return services.close_ticket(tid, body.method, user)


class VoidBody(BaseModel):
    reason: str = Field(default="", max_length=200)


@app.post("/api/tickets/{tid}/void")
def void(tid: int, body: VoidBody, user: dict = Depends(current_user)):
    return services.void_ticket(tid, body.reason, user)


class MoveBody(BaseModel):
    slot_id: int


@app.post("/api/tickets/{tid}/move")
def move(tid: int, body: MoveBody, user: dict = Depends(current_user)):
    return services.move_ticket(tid, body.slot_id, user)


def _svg_qr(payload: str) -> Response:
    import segno

    buf = io.BytesIO()
    segno.make(payload, error="m").save(buf, kind="svg", scale=8, border=2, dark="#0b1220", light="#ffffff",
                                        xmldecl=False, svgns=True)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/tickets/{tid}/upi.svg")
def upi_qr(tid: int, user: dict = Depends(current_user)):
    t = services.ticket_detail(tid)
    with db.read() as conn:
        st = services.settings(conn)
    if not st["upi_id"]:
        raise services.Conflict("Add a UPI ID in Settings to show payment QR codes.")
    amount = t["quote"]["total"] if t["quote"] else (t["fare"] or 0)
    uri = (f"upi://pay?pa={quote(st['upi_id'], safe='@.')}&pn={quote(st['payee_name'])}&am={amount:.2f}"
           f"&cu=INR&tn={quote('Parking ' + t['code'])}")
    return _svg_qr(uri)


@app.get("/api/tickets/{tid}/code.svg")
def ticket_qr(tid: int, user: dict = Depends(current_user)):
    return _svg_qr(services.ticket_detail(tid)["code"])


# ------------------------------------------------------------------ lot camera / layout

@app.post("/api/lot/scan")
async def lot_scan(image: UploadFile | None = File(None), sample: str | None = Form(None),
                   user: dict = Depends(current_user)):
    data = await _read_upload(image)
    return await run_in_threadpool(services.scan, data, sample, user)


@app.post("/api/lot/calibrate")
async def lot_calibrate(image: UploadFile | None = File(None), sample: str | None = Form(None),
                        user: dict = Depends(admin_user)):
    data = await _read_upload(image)
    return await run_in_threadpool(services.calibrate, data, sample, user)


@app.post("/api/lot/clear-camera")
def lot_clear(user: dict = Depends(current_user)):
    services.clear_camera(user)
    return {"ok": True}


class SlotPatch(BaseModel):
    kind: str | None = None
    enabled: bool | None = None


@app.patch("/api/slots/{sid}")
def patch_slot(sid: int, body: SlotPatch, user: dict = Depends(admin_user)):
    return services.update_slot(sid, body.model_dump(exclude_none=True), user)


@app.get("/media")
def media(src: str, user: dict = Depends(current_user)):
    p = services.resolve_media(src)
    if not p:
        raise services.NotFound("Image not found.")
    return FileResponse(p, headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------------ settings / team

@app.put("/api/settings")
def put_settings(body: dict, user: dict = Depends(admin_user)):
    with db.tx() as conn:
        st = services.update_settings(conn, body, user)
    bus.publish("settings")
    return st


@app.get("/api/users")
def users(user: dict = Depends(admin_user)):
    with db.read() as conn:
        return db.rows(conn.execute("SELECT id, username, name, role, active, created_at FROM users ORDER BY id"))


class NewUser(SetupBody):
    role: str = "operator"


@app.post("/api/users")
def add_user(body: NewUser, user: dict = Depends(admin_user)):
    if body.role not in ("admin", "operator"):
        raise ValueError("Role must be admin or operator.")
    security.check_password_rules(body.password)
    uname = body.username.strip().lower()
    if not uname.replace("_", "").replace(".", "").isalnum():
        raise ValueError("Username can use letters, numbers, dots and underscores.")
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (uname,)).fetchone():
            raise services.Conflict("That username is taken.")
        conn.execute("INSERT INTO users(username,name,pw_hash,role,created_at) VALUES (?,?,?,?,?)",
                     (uname, body.name.strip(), security.hash_password(body.password), body.role, db.now()))
        db.log(conn, "user", f"{user['name']} added {body.role} {body.name.strip()}", user_id=user["id"])
    return {"ok": True}


class UserPatch(BaseModel):
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


@app.patch("/api/users/{uid}")
def patch_user(uid: int, body: UserPatch, user: dict = Depends(admin_user)):
    with db.tx() as conn:
        target = db.one(conn.execute("SELECT * FROM users WHERE id=?", (uid,)))
        if not target:
            raise services.NotFound("User not found.")
        if body.active is not None:
            if uid == user["id"] and not body.active:
                raise ValueError("You can't deactivate yourself.")
            conn.execute("UPDATE users SET active=? WHERE id=?", (1 if body.active else 0, uid))
            if not body.active:
                conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
        if body.password:
            security.check_password_rules(body.password)
            conn.execute("UPDATE users SET pw_hash=? WHERE id=?", (security.hash_password(body.password), uid))
            conn.execute("DELETE FROM auth_sessions WHERE user_id=? AND ? != ?", (uid, uid, user["id"]))
    return {"ok": True}


# ------------------------------------------------------------------ assistant

class ChatBody(BaseModel):
    messages: list[dict] = Field(max_length=40)


@app.post("/api/assistant")
def chat(body: ChatBody, user: dict = Depends(current_user)):
    return StreamingResponse(iterate_in_threadpool(assistant.stream(body.messages)), media_type="text/plain; charset=utf-8")


# ------------------------------------------------------------------ web app

app.mount("/static", StaticFiles(directory=config.WEB), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    html = (config.WEB / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("{{v}}", __version__ + "-" + str(int((config.WEB / "app.js").stat().st_mtime))),
                        headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico")
def favicon():
    return FileResponse(config.WEB / "icon.svg", media_type="image/svg+xml")
