from __future__ import annotations

import re

from scraper.platform import hostname, platform_from_url

DISTANCE_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*(?:km|kms|kilometers?|m|meters?|away)\s*$", re.I)
DISTANCE_INLINE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(km|kms|kilometers?)\b", re.I)


def is_distance_text(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if DISTANCE_RE.match(text):
        return True
    return bool(re.fullmatch(r"\d+(?:\.\d+)?\s*km(?:s)?(?:\s+away)?", text, re.I))


def distance_km_from_text(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    match = DISTANCE_INLINE_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def place_text(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip() and not is_distance_text(part))


def platform_url_fields(source_url: str | None, extra: dict | None = None) -> dict[str, str | None]:
    """Map a URL onto only the matching platform URL slot. Never copy across platforms."""
    slots = {"swiggy_url": None, "zomato_url": None, "magicpin_url": None, "district_url": None}
    extra = extra or {}
    candidates = [source_url, extra.get("swiggy_url"), extra.get("zomato_url"), extra.get("magicpin_url"), extra.get("district_url")]
    for url in candidates:
        if not isinstance(url, str) or not url.strip():
            continue
        host = hostname(url)
        if host.endswith("district.in"):
            slots["district_url"] = url.strip()
            continue
        platform = platform_from_url(url)
        if platform == "swiggy":
            slots["swiggy_url"] = url.strip()
        elif platform == "zomato":
            slots["zomato_url"] = url.strip()
        elif platform == "magicpin":
            slots["magicpin_url"] = url.strip()
    return slots
