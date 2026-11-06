"""Password hashing (scrypt), opaque session tokens and login throttling."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from . import config, db

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                            dklen=len(bytes.fromhex(digest)))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


def check_password_rules(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if password.lower() == password and password.isalpha():
        raise ValueError("Use a mix of letters and numbers or symbols.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    t = db.now()
    conn.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (t,))
    conn.execute("INSERT INTO auth_sessions(token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                 (_token_hash(token), user_id, t, t + config.SESSION_DAYS * 86400))
    return token


def user_for_token(conn, token: str | None) -> dict | None:
    if not token:
        return None
    return db.one(conn.execute(
        "SELECT u.id, u.username, u.name, u.role FROM auth_sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1",
        (_token_hash(token), db.now())))


def drop_session(conn, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))


class Throttle:
    """5 failed logins per (user, ip) -> 60 s lockout."""

    def __init__(self, limit: int = 5, window: int = 300, lockout: int = 60) -> None:
        self.limit, self.window, self.lockout = limit, window, lockout
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        with self._lock:
            now = time.time()
            fails = [t for t in self._fails.get(key, []) if now - t < self.window]
            self._fails[key] = fails
            if len(fails) >= self.limit:
                wait = int(self.lockout - (now - fails[-1]))
                return max(0, wait)
            return 0

    def fail(self, key: str) -> None:
        with self._lock:
            self._fails.setdefault(key, []).append(time.time())

    def clear(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


throttle = Throttle()
