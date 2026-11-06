"""Paths and environment settings. Everything operators can change at runtime lives in the DB instead."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # optional .env next to the project
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass

DATA = Path(os.environ.get("SMARTPARK_DATA", ROOT / "data"))
IMAGES = DATA / "images"
DB_PATH = DATA / "smartpark.db"
MODEL_PATH = ROOT / "model" / "best.pt"
ASSETS = ROOT / "assets"
SAMPLES = ASSETS / "samples"
WEB = ROOT / "web"

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5000"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview").strip()

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
SESSION_DAYS = 7
SESSION_COOKIE = "sp_session"
# Camera observations older than this no longer block slot assignment.
CAMERA_STALE_SECONDS = 6 * 3600

DISABLE_VISION = os.environ.get("SMARTPARK_DISABLE_VISION") == "1"

for d in (DATA, IMAGES):
    d.mkdir(parents=True, exist_ok=True)
