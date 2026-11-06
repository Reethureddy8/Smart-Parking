"""End-to-end API flows with vision disabled."""
import pytest
from fastapi.testclient import TestClient

from smartpark import db
from smartpark.main import app

H = {"X-SmartPark": "1"}


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        r = client.post("/api/setup", json={"name": "Asha Admin", "username": "asha", "password": "parking123",
                                            "lot_name": "Test Lot"}, headers=H)
        assert r.status_code == 200, r.text
        yield client


def test_csrf_header_required(c):
    assert c.post("/api/tickets", json={"plate": "KA01AB1234"}).status_code == 403


def test_setup_only_once(c):
    r = c.post("/api/setup", json={"name": "x", "username": "x", "password": "parking123"}, headers=H)
    assert r.status_code == 409


def test_me_and_lot(c):
    me = c.get("/api/me").json()
    assert me["user"]["role"] == "admin" and me["settings"]["lot_name"] == "Test Lot"
    lot = c.get("/api/lot").json()
    assert lot["capacity"] == 16 and lot["counts"]["free"] == 16


def test_ticket_lifecycle(c):
    pv = c.get("/api/assign/preview?vehicle_class=car").json()["slot"]
    t = c.post("/api/tickets", json={"plate": "ka 01 ab 1234", "vehicle_class": "car"}, headers=H).json()
    assert t["plate"] == "KA01AB1234" and t["slot_label"] == pv["label"] and t["route"]["points"]
    r = c.post("/api/tickets", json={"plate": "KA01AB1234"}, headers=H)  # duplicate
    assert r.status_code == 409 and r.json()["ticket_id"] == t["id"]
    t2 = c.post("/api/tickets", json={"plate": "TS09EZ7777"}, headers=H).json()
    assert t2["slot_id"] != t["slot_id"]
    assert c.get("/api/tickets/find?q=7777").json()["ticket"]["id"] == t2["id"]
    free = [s for s in c.get("/api/lot").json()["slots"] if s["status"] == "free"][-1]
    moved = c.post(f"/api/tickets/{t2['id']}/move", json={"slot_id": free["id"]}, headers=H).json()
    assert moved["slot_label"] == free["label"]
    with db.tx() as conn:  # pretend it parked 2.5 hours
        conn.execute("UPDATE tickets SET entry_at = entry_at - 9000 WHERE id=?", (t["id"],))
    closed = c.post(f"/api/tickets/{t['id']}/close", json={"method": "cash"}, headers=H).json()
    assert closed["status"] == "closed" and closed["fare"] == 80
    assert c.post(f"/api/tickets/{t['id']}/close", json={"method": "cash"}, headers=H).status_code == 409
    hist = c.get("/api/tickets?status=history").json()
    assert hist["total"] == 1 and hist["revenue"] == 80
    assert "KA 01 AB 1234" in c.get("/api/tickets/export.csv").text
    st = c.get("/api/stats").json()
    assert st["revenue_today"] == 80 and st["counts"]["parked"] == 1


def test_ev_prefers_ev_bay(c):
    lot = c.get("/api/lot").json()
    far = [s for s in lot["slots"] if s["status"] == "free"][-1]
    assert c.patch(f"/api/slots/{far['id']}", json={"kind": "ev"}, headers=H).status_code == 200
    t = c.post("/api/tickets", json={"plate": "DL3CAB0001", "vehicle_class": "ev"}, headers=H).json()
    assert t["slot_id"] == far["id"]
    assert c.get("/api/assign/preview?vehicle_class=car").json()["slot"]["kind"] == "standard"


def test_operator_permissions(c):
    r = c.post("/api/users", json={"name": "Op", "username": "op1", "password": "gate4567", "role": "operator"}, headers=H)
    assert r.status_code == 200
    op = TestClient(app)
    assert op.post("/api/login", json={"username": "op1", "password": "gate4567"}, headers=H).status_code == 200
    assert op.put("/api/settings", json={"lot_name": "x"}, headers=H).status_code == 403
    t = op.post("/api/tickets", json={"plate": "MH12XY9876"}, headers=H).json()
    assert op.post(f"/api/tickets/{t['id']}/close", json={"method": "waived"}, headers=H).status_code == 403
    assert op.post(f"/api/tickets/{t['id']}/void", json={"reason": "x"}, headers=H).status_code == 403
    assert c.post(f"/api/tickets/{t['id']}/void", json={"reason": "test"}, headers=H).json()["status"] == "void"


def test_login_throttle(c):
    bad = TestClient(app)
    codes = [bad.post("/api/login", json={"username": "asha", "password": "nope"}, headers=H).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_settings_validation_and_upi(c):
    assert c.put("/api/settings", json={"upi_id": "not a upi"}, headers=H).status_code == 400
    assert c.put("/api/settings", json={"upi_id": "smartpark@okaxis"}, headers=H).status_code == 200
    t = c.get("/api/tickets?status=parked").json()["items"][0]
    r = c.get(f"/api/tickets/{t['id']}/upi.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")


def test_vision_disabled_is_clear_error(c):
    r = c.post("/api/lot/scan", data={"sample": "lot-a.jpg"}, headers=H)
    assert r.status_code == 503 and "Vision" in r.json()["error"]


def test_media_path_traversal_blocked(c):
    assert c.get("/media?src=data:../smartpark.db").status_code == 404
    assert c.get("/media?src=asset:lot.jpg").status_code == 200


def test_assistant_offline(c):
    r = c.post("/api/assistant", json={"messages": [{"role": "user", "content": "how many bays are free?"}]}, headers=H)
    assert "free" in r.text


def test_unauthenticated(c):
    assert TestClient(app).get("/api/lot").status_code == 401
