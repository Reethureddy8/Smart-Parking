"""Tariffs. Pure functions so the rules are easy to test and explain."""
from __future__ import annotations

import math

VEHICLE_CLASSES = {
    "car": "Car",
    "bike": "Two-wheeler",
    "ev": "Electric car",
    "large": "Van / SUV",
}

DEFAULT_TARIFFS = {
    "car":   {"grace_min": 10, "first_hour": 40, "per_hour": 20, "daily_cap": 300},
    "bike":  {"grace_min": 10, "first_hour": 20, "per_hour": 10, "daily_cap": 120},
    "ev":    {"grace_min": 10, "first_hour": 40, "per_hour": 20, "daily_cap": 300},
    "large": {"grace_min": 10, "first_hour": 60, "per_hour": 30, "daily_cap": 450},
}


def normalise_tariff(t: dict) -> dict:
    out = {}
    for key in ("grace_min", "first_hour", "per_hour", "daily_cap"):
        v = float(t.get(key, 0))
        if not math.isfinite(v) or v < 0 or v > 1_000_000:
            raise ValueError(f"{key} must be a non-negative number")
        out[key] = int(v) if key == "grace_min" else round(v, 2)
    return out


def _day_charge(minutes: float, t: dict) -> float:
    if minutes <= 0:
        return 0.0
    extra_hours = math.ceil(max(0.0, minutes - 60) / 60)
    return min(t["daily_cap"], t["first_hour"] + extra_hours * t["per_hour"])


def compute_fare(minutes: float, t: dict) -> dict:
    """Fare for a stay of `minutes`.

    - Free within the grace period.
    - Otherwise first hour flat, then each started hour, capped per 24h block.
    """
    minutes = max(0.0, float(minutes))
    lines: list[str] = []
    if minutes <= t["grace_min"]:
        return {"total": 0.0, "lines": [f"Within {t['grace_min']} min grace period"], "free": True}
    days, rem = divmod(minutes, 1440)
    days = int(days)
    total = 0.0
    if days:
        total += days * t["daily_cap"]
        lines.append(f"{days} full day{'s' if days > 1 else ''} x daily cap")
    if rem > 0:
        day = _day_charge(rem, t)
        total += day
        if day >= t["daily_cap"] and rem > 60:
            lines.append("Daily cap reached")
        else:
            lines.append("First hour")
            extra = math.ceil(max(0.0, rem - 60) / 60)
            if extra:
                lines.append(f"{extra} additional hour{'s' if extra > 1 else ''}")
    return {"total": round(total, 2), "lines": lines, "free": False}
