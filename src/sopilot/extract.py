"""Identifier, product and language extraction (deterministic)."""
from __future__ import annotations

import re

SERVICE_TAG = re.compile(r"\b(HDN[A-Z0-9]{6})\b", re.IGNORECASE)
ORDER = re.compile(r"\bORD[-\s]?(\d{8})\b", re.IGNORECASE)
CASE = re.compile(r"\b(?:CS-|case\s*#\s*)(\d{7})\b", re.IGNORECASE)

PRODUCT_PATTERNS = {
    "laptop": r"\b(?:aero ?1[345]|forge ?16)\b",
    "desktop": r"\b(?:tower ?t5|mini ?m2)\b",
    "monitor": r"\bclarity ?(?:27|32)\b",
    "dock": r"\bdock ?d3\b",
    "server": r"\b(?:stratus ?s[24]|vault ?v1)\b",
}
_PROD = {k: re.compile(v, re.IGNORECASE) for k, v in PRODUCT_PATTERNS.items()}


def extract_fields(text: str) -> dict:
    out = {}
    m = SERVICE_TAG.search(text)
    if m:
        out["service_tag"] = m.group(1).upper()
    m = ORDER.search(text)
    if m:
        out["order_number"] = "ORD-" + m.group(1)
    m = CASE.search(text)
    if m:
        out["case_number"] = "CS-" + m.group(1)
    return out


def extract_product(text: str) -> dict:
    for fam, p in _PROD.items():
        m = p.search(text)
        if m:
            return {"family": fam, "mention": m.group(0)}
    return {"family": None, "mention": None}


# Tiny language identifier for the four pilot languages: stopwords plus
# distinctive letters. Measured against gold labels in the evaluation.
_STOP = {
    "en": set("the and is my i to it of for on with this not can you have was but be are at a an in".split()),
    "pl": set("się nie jest mój moje mojego na do jak w z i że czy po już za proszę dzień dobry".split()),
    "de": set("der die das und ist nicht mein meine ich ein eine mit für auf wie bitte ist den dem nach".split()),
    "es": set("el la los las de y es mi no se que en por un una para con me ha hace cuándo cómo".split()),
}
_CHARS = {"pl": "ąćęłńśźż", "de": "äöüß", "es": "ñ¿¡áéíóú"}


def detect_language(text: str) -> str:
    words = re.findall(r"[^\W\d_]+", text.lower())
    if not words:
        return "en"
    score = {k: sum(w in s for w in words) for k, s in _STOP.items()}
    low = text.lower()
    for k, chars in _CHARS.items():
        score[k] += 2 * sum(low.count(c) for c in chars)
    best = max(score, key=score.get)
    return best if score[best] > 0 else "en"
