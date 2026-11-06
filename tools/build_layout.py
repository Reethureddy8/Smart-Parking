"""Regenerate assets/layout.json from assets/lot.jpg using the YOLO model."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from smartpark.layout import Det, build_layout  # noqa: E402

img = cv2.imread(str(ROOT / "assets" / "samples" / "lot-a.jpg"))  # native 416px frame of the same view
shown = cv2.imread(str(ROOT / "assets" / "lot.jpg"))
h, w = img.shape[:2]
m = YOLO(str(ROOT / "model" / "best.pt"))
res = m(img, imgsz=416, conf=0.25, verbose=False)[0]
dets = [Det(*(float(v) for v in (b.xyxy[0][0] / w, b.xyxy[0][1] / h, b.xyxy[0][2] / w, b.xyxy[0][3] / h)),
            "car" if res.names[int(b.cls)].lower() == "car" else "empty", float(b.conf)) for b in res.boxes]
lay = build_layout(dets)
lay["lot_image"] = {"src": "asset:lot.jpg", "w": shown.shape[1], "h": shown.shape[0]}
(ROOT / "assets" / "layout.json").write_text(json.dumps(lay, indent=1))
for s in lay["slots"]:
    print(s["label"], s["seen"], [round(s[k], 3) for k in ("x1", "y1", "x2", "y2")])
print(lay["orientation"], len(lay["slots"]), "bays")
