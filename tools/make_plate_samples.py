"""Generate synthetic vehicle-front images with Indian plates for trying the entry flow."""
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "assets" / "plates"
OUT.mkdir(parents=True, exist_ok=True)


def car_front(plate_lines: list[str], name: str, body=(70, 60, 160), seed=0) -> None:
    rng = np.random.default_rng(seed)
    img = np.full((720, 1080, 3), (190, 196, 200), np.uint8)
    img[:] = img + rng.integers(-12, 12, img.shape, dtype=np.int16).clip(-12, 12).astype(np.uint8) * 0
    cv2.rectangle(img, (0, 560), (1080, 720), (90, 92, 96), -1)  # road
    cv2.rectangle(img, (150, 170), (930, 600), body, -1, cv2.LINE_AA)  # body
    cv2.rectangle(img, (230, 90), (850, 250), tuple(int(c * 0.6) for c in body), -1, cv2.LINE_AA)  # cabin
    cv2.rectangle(img, (260, 110), (820, 235), (60, 50, 40), -1, cv2.LINE_AA)  # windscreen
    for cx in (240, 840):
        cv2.ellipse(img, (cx, 330), (70, 38), 0, 0, 360, (225, 235, 240), -1, cv2.LINE_AA)  # lamps
    cv2.rectangle(img, (330, 300), (750, 380), (35, 35, 38), -1)  # grille
    cv2.putText(img, "SMARTCAR", (430, 285), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (210, 210, 215), 2, cv2.LINE_AA)
    two = len(plate_lines) == 2
    x1, y1, x2, y2 = (420, 420, 660, 540) if two else (340, 440, 740, 520)
    cv2.rectangle(img, (x1, y1), (x2, y2), (250, 250, 250), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (20, 20, 20), 3)
    for i, line in enumerate(plate_lines):
        scale = 1.45 if two else 1.55
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_DUPLEX, scale, 3)
        ty = y1 + (50 if two else 58) + i * 55
        cv2.putText(img, line, ((x1 + x2 - tw) // 2, ty), cv2.FONT_HERSHEY_DUPLEX, scale, (15, 15, 15), 3, cv2.LINE_AA)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    cv2.imwrite(str(OUT / name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


car_front(["KA 01 AB 1234"], "car-ka01ab1234.jpg", (60, 50, 150), 1)
car_front(["AP 39 CQ 0420"], "car-ap39cq0420.jpg", (140, 110, 40), 2)
car_front(["TS 09", "EZ 7777"], "car-ts09ez7777-two-line.jpg", (40, 120, 60), 3)
print("written to", OUT)
