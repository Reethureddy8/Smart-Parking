"""Number-plate text handling: cleaning, OCR-error correction and formatting.

Indian plates follow  SS DD XXX NNNN  (state, district, series, number) or the
Bharat series  YY BH NNNN XX.  OCR routinely confuses look-alike glyphs, so we
fit raw text into those templates position by position, fixing only characters
whose class (letter vs digit) is wrong, and score each fit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "J": "1",
            "Z": "2", "S": "5", "B": "8", "G": "6", "T": "7", "A": "4"}
TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "7": "T", "4": "A", "3": "B"}

STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP", "HR", "JH",
    "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY",
    "RJ", "SK", "TN", "TR", "TS", "TG", "UK", "UA", "UP", "WB",
}

_STANDARD = re.compile(r"^([A-Z]{2})(\d{2})([A-Z]{0,3})(\d{4})$")
_BH = re.compile(r"^(\d{2})(BH)(\d{4})([A-Z]{1,2})$")


def clean(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _coerce(chars: str, kind: str) -> tuple[str, int] | None:
    """Force every char to `kind` ('L' letter / 'D' digit). Returns (text, substitutions)."""
    out, subs = [], 0
    for ch in chars:
        if kind == "D":
            if ch.isdigit():
                out.append(ch)
            elif ch in TO_DIGIT:
                out.append(TO_DIGIT[ch]); subs += 1
            else:
                return None
        else:
            if ch.isalpha():
                out.append(ch)
            elif ch in TO_LETTER:
                out.append(TO_LETTER[ch]); subs += 1
            else:
                return None
    return "".join(out), subs


@dataclass
class PlateFit:
    plate: str
    score: float  # 0..1, how plausible as a real plate
    standard: bool
    corrections: int


def fit(raw: str) -> PlateFit | None:
    """Best template fit for raw OCR text, or None if it cannot be a plate."""
    s = clean(raw)
    # Every real plate has several digits; words like brand badges don't.
    if not 4 <= len(s) <= 12 or sum(c.isdigit() for c in s) < 2:
        return None
    best: PlateFit | None = None

    def consider(plate: str, subs: int, bonus: float) -> None:
        nonlocal best
        score = max(0.0, min(1.0, 0.82 - 0.1 * subs + bonus))
        cand = PlateFit(plate, score, True, subs)
        if best is None or cand.score > best.score:
            best = cand

    # Standard: 2 letters, 1-2 digits, 0-3 letters, 1-4 digits.
    for dlen in (2, 1):
        for slen in (0, 1, 2, 3):
            for nlen in (4, 3, 2, 1):
                if 2 + dlen + slen + nlen != len(s):
                    continue
                parts = [(s[0:2], "L"), (s[2:2 + dlen], "D"),
                         (s[2 + dlen:2 + dlen + slen], "L"), (s[2 + dlen + slen:], "D")]
                fixed, subs = [], 0
                for chunk, kind in parts:
                    r = _coerce(chunk, kind)
                    if r is None:
                        break
                    fixed.append(r[0]); subs += r[1]
                else:
                    district = fixed[1].zfill(2)
                    plate = fixed[0] + district + fixed[2] + fixed[3]
                    bonus = 0.15 if fixed[0] in STATE_CODES else -0.2
                    bonus -= 0.08 * (4 - nlen)
                    bonus -= 0.04 if dlen == 1 else 0
                    bonus += 0.03 if slen in (1, 2) else 0
                    consider(plate, subs, bonus)

    # Bharat series: YY BH NNNN X(X)
    for tail in (1, 2):
        if len(s) == 8 + tail:
            parts = [(s[0:2], "D"), (s[2:4], "L"), (s[4:8], "D"), (s[8:], "L")]
            fixed, subs = [], 0
            for chunk, kind in parts:
                r = _coerce(chunk, kind)
                if r is None:
                    break
                fixed.append(r[0]); subs += r[1]
            else:
                if fixed[1] == "BH":
                    consider("".join(fixed), subs, 0.15)

    if best is None and 5 <= len(s) <= 10 and any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
        best = PlateFit(s, 0.35, False, 0)  # foreign / non-standard plate
    if best and best.score < 0.3:
        return None
    return best


def is_standard(plate: str) -> bool:
    p = clean(plate)
    return bool(_STANDARD.match(p) or _BH.match(p))


def pretty(plate: str) -> str:
    """'KA01AB1234' -> 'KA 01 AB 1234'."""
    p = clean(plate)
    m = _STANDARD.match(p)
    if m:
        return " ".join(g for g in m.groups() if g)
    m = _BH.match(p)
    if m:
        return " ".join(m.groups())
    return p


def validate_manual(text: str) -> str:
    """Normalise operator-typed plates. Raises ValueError when unusable."""
    p = clean(text)
    if not 4 <= len(p) <= 12:
        raise ValueError("Plate must have 4 to 12 letters or digits.")
    if not any(c.isdigit() for c in p):
        raise ValueError("Plate must contain at least one digit.")
    return p
