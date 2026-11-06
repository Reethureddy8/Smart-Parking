"""Computer vision: lot occupancy (YOLO, best.pt) and plate reading (EasyOCR).

Models load on a background thread so the web app is usable immediately;
manual plate entry works while they warm up.
"""
from __future__ import annotations

import itertools
import logging
import threading
import time

import numpy as np

from . import config, plates
from .layout import Det

log = logging.getLogger("smartpark.vision")

ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
YOLO_IMGSZ = 416  # the size best.pt was trained at; larger sizes miss empty bays


class Vision:
    def __init__(self) -> None:
        self.state = "idle"  # idle | loading | ready | error | disabled
        self.detail = ""
        self.yolo = None
        self.ocr = None
        self._lock = threading.Lock()
        self.loaded_at: float | None = None

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if config.DISABLE_VISION:
            self.state, self.detail = "disabled", "Vision disabled by SMARTPARK_DISABLE_VISION"
            return
        if self.state in ("loading", "ready"):
            return
        self.state, self.detail = "loading", "Loading detection and OCR models"
        threading.Thread(target=self._load, name="vision-loader", daemon=True).start()

    def _load(self) -> None:
        t0 = time.time()
        try:
            from ultralytics import YOLO

            self.yolo = YOLO(str(config.MODEL_PATH))
            self.yolo(np.zeros((YOLO_IMGSZ, YOLO_IMGSZ, 3), np.uint8), imgsz=YOLO_IMGSZ, verbose=False)
            import easyocr

            self.ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
            self.state, self.detail = "ready", f"Models ready in {time.time() - t0:.0f}s"
            self.loaded_at = time.time()
            log.info(self.detail)
        except Exception as exc:  # pragma: no cover - environment dependent
            log.exception("vision load failed")
            self.state, self.detail = "error", f"{type(exc).__name__}: {exc}"

    def status(self) -> dict:
        return {"state": self.state, "detail": self.detail}

    def _require(self) -> None:
        if self.state != "ready":
            raise RuntimeError("Vision models are still loading. Try again in a moment, or enter the plate manually."
                               if self.state == "loading" else f"Vision unavailable: {self.detail or self.state}")

    # ------------------------------------------------------------ lot camera
    def detect_lot(self, img: np.ndarray, conf: float = 0.25) -> list[Det]:
        self._require()
        h, w = img.shape[:2]
        with self._lock:
            res = self.yolo(img, imgsz=YOLO_IMGSZ, conf=conf, verbose=False)[0]
        names = res.names
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
            label = str(names[int(b.cls)]).lower()
            out.append(Det(x1 / w, y1 / h, x2 / w, y2 / h, "car" if label == "car" else "empty", float(b.conf)))
        return out

    # ------------------------------------------------------------ plates
    def read_plate(self, img: np.ndarray) -> dict:
        """Return ranked plate candidates plus the region they came from."""
        self._require()
        import cv2

        h, w = img.shape[:2]
        scale = min(1.0, 1280 / max(h, w))
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        # Fast pass first; magnify only if no proper plate turned up (small / distant plates).
        for mag in (1.0, 1.6):
            with self._lock:
                raw = self.ocr.readtext(gray, allowlist=ALNUM, detail=1, paragraph=False,
                                        width_ths=0.9, mag_ratio=mag)
            boxes = []
            for bbox, text, conf in raw:
                xs = [float(p[0]) for p in bbox]; ys = [float(p[1]) for p in bbox]
                t = plates.clean(text)
                if t:
                    boxes.append({"text": t, "conf": float(conf), "x1": min(xs), "y1": min(ys),
                                  "x2": max(xs), "y2": max(ys)})
            cands = rank_candidates(boxes)
            if any(c["standard"] and c["score"] >= 0.6 for c in cands):
                break
        return {"candidates": cands, "tokens": [b["text"] for b in boxes],
                "size": [img.shape[1], img.shape[0]], "scale": scale}


def _neighbours(a: dict, b: dict) -> bool:
    """Same plate: side by side on one line, or stacked (two-line plates)."""
    ha, hb = a["y2"] - a["y1"], b["y2"] - b["y1"]
    hm = max(ha, hb, 1)
    if abs(ha - hb) > 0.6 * hm:
        return False
    same_line = abs((a["y1"] + a["y2"]) / 2 - (b["y1"] + b["y2"]) / 2) < 0.5 * hm and \
        -0.3 * hm < b["x1"] - a["x2"] < 1.6 * hm
    stacked = 0 <= b["y1"] - a["y2"] < 0.8 * hm and \
        min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]) > 0.3 * min(a["x2"] - a["x1"], b["x2"] - b["x1"])
    return same_line or stacked


def rank_candidates(boxes: list[dict], top: int = 3) -> list[dict]:
    """Score single tokens and adjacent token groups as plates."""
    order = sorted(boxes, key=lambda b: (round(b["y1"] / 10), b["x1"]))
    groups: list[list[dict]] = [[b] for b in order]
    for n in (2, 3):
        for combo in itertools.permutations(order, n):
            if all(_neighbours(combo[i], combo[i + 1]) for i in range(n - 1)):
                groups.append(list(combo))
    best: dict[str, dict] = {}
    for g in groups:
        text = "".join(b["text"] for b in g)
        f = plates.fit(text)
        if not f:
            continue
        ocr = sum(b["conf"] for b in g) / len(g)
        score = round(0.6 * f.score + 0.4 * ocr, 4)
        if f.plate not in best or score > best[f.plate]["score"]:
            best[f.plate] = {
                "plate": f.plate, "display": plates.pretty(f.plate), "score": score,
                "ocr_conf": round(ocr, 3), "standard": f.standard, "corrections": f.corrections,
                "raw": " ".join(b["text"] for b in g),
                "box": [min(b["x1"] for b in g), min(b["y1"] for b in g),
                        max(b["x2"] for b in g), max(b["y2"] for b in g)],
            }
    return sorted(best.values(), key=lambda c: -c["score"])[:top]


vision = Vision()
