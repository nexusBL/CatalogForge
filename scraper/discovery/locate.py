from __future__ import annotations

import re
from pathlib import Path

from scraper.discovery.location import parse_location
from scraper.discovery.models import CatalogueKind, LocationQuery
from scraper.discovery.urls import join_url, picker_query, type_query

LOCATE_JS = Path(__file__).with_name("locate.js").read_text(encoding="utf-8")

MAGICPIN_LOCATION = re.compile(r'class=["\'][^"\']*selectedLocation[^"\']*["\']', re.I)
SWIGGY_LOCATION = re.compile(
    r"Setup your precise location|precise location|Enter your delivery location|Use my current location|SEARCH RESULT",
    re.I,
)
ZOMATO_LOCATION = re.compile(
    r"Search for restaurant, cuisine|locationDropDown|header-location|role=['\"]option['\"]",
    re.I,
)
SUGGESTION_RE = re.compile(
    r"""<(?:div|li|span|button|a)[^>]*(?:role=["']option["']|class=["'][^"']*(?:suggestion|autocomplete|place-item|Location-sc-|LocationBlock)[^"']*["'])[^>]*>\s*([^<]{2,160})""",
    re.I,
)

CATEGORY_LABELS = {
    ("magicpin", "restaurant"): ("Food Delivery",),
    ("magicpin", "dineout"): ("Budget Dining", "Fine Dining"),
    ("swiggy", "restaurant"): ("Food Delivery", "FOOD DELIVERY", "Order Online"),
    ("swiggy", "dineout"): ("Dineout", "DINEOUT"),
    ("zomato", "restaurant"): ("Delivery",),
    ("zomato", "dineout"): ("Dining Out", "Dining", "dine-out"),
}

CARD_RE = re.compile(
    r"""<(?:a|button|div)[^>]*>[\s\S]{0,400}?(Food Delivery|Budget Dining|Fine Dining|Order Online|Dineout|Dining Out)[\s\S]{0,200}?</(?:a|button|div)>""",
    re.I,
)
DISCOVERY_IMG_RE = re.compile(
    r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>[\s\S]{0,1500}?<img\b[^>]*alt=["']([^"']+)["']""",
    re.I,
)
MAGICPIN_ALT = {
    "restaurant": ("food delivery", "food-delivery"),
    "budget": ("budget dining", "budget eats"),
    "fine": ("fine dining", "fine-dine"),
}


def is_location_picker_page(html: str, platform: str) -> bool:
    blob = html or ""
    if platform == "magicpin":
        return bool(MAGICPIN_LOCATION.search(blob))
    if platform == "swiggy":
        return bool(SWIGGY_LOCATION.search(blob))
    if platform == "zomato":
        return bool(ZOMATO_LOCATION.search(blob) or re.search(r"/dine-out", blob, re.I))
    return False


_SWIGGY_HEADER_SKIP = re.compile(
    r"^(other|setup your precise location|precise location|select location|search for area|"
    r"cart|sign in|help|offers|search|swiggy corporate|new|\d+)$",
    re.I,
)


def query_tokens(query: str) -> list[str]:
    return [part for part in re.split(r"[,\s/|]+", (query or "").lower()) if len(part) > 1]


def parse_swiggy_header_location(text: str) -> str:
    """Read the address under the Swiggy header chip (often 'Other' plus a second line)."""
    for line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line or _SWIGGY_HEADER_SKIP.match(line):
            continue
        if "," in line and 4 < len(line) < 180:
            return line
    for line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line or _SWIGGY_HEADER_SKIP.match(line):
            continue
        if 2 < len(line) < 80:
            return line
    return ""


def _fold_place(text: str) -> str:
    hay = re.sub(r"[,\s/|]+", " ", (text or "").strip().lower())
    hay = hay.replace("bengaluru", "bangalore").replace("mangaluru", "mangalore")
    return hay.strip()


def _place_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold_place(text))


def _locality_in_place(hay: str, loc: str) -> bool:
    if not loc:
        return True
    if loc in hay:
        return True
    key = _place_key(loc)
    return bool(key) and key in _place_key(hay)


def location_is_consistent(requested: str, selected: str) -> bool:
    hay = _fold_place(selected)
    if not hay:
        return False
    try:
        parsed = parse_location(requested)
    except ValueError:
        parsed = None
    locality = _fold_place(parsed.locality) if parsed and parsed.locality else ""
    city = _fold_place(parsed.city) if parsed and parsed.city else ""
    if locality:
        if not _locality_in_place(hay, locality):
            return False
        if city and _city_in_place(hay, city):
            return True
        compact = _fold_place(selected)
        return compact == locality or compact.startswith(locality)
    if city:
        return _city_in_place(hay, city)
    wanted = query_tokens(requested)
    if not wanted:
        return False
    folded = [_fold_place(token) for token in wanted]
    hits = sum(1 for token in folded if token and token in hay)
    need = 2 if len(folded) >= 2 else 1
    if hits >= need:
        return True
    first = next((token for token in folded if token), "")
    return bool(first and first in hay)


def _city_in_place(hay: str, city: str) -> bool:
    token = _fold_place(city)
    if not token or not hay:
        return False
    aliases = {token}
    if token in {"bangalore", "bengaluru"}:
        aliases.update({"bangalore", "bengaluru"})
    if token in {"mangalore", "mangaluru"}:
        aliases.update({"mangalore", "mangaluru"})
    return any(alias in hay for alias in aliases)


_RESTAURANT_HINT = re.compile(
    r"\b(restaurant|cafe|hotel|dhaba|biryani|kitchen|pizza|burger|bar|lounge|bakery|nandos|kfc|domino|mall|landmark)\b",
    re.I,
)
_ROAD_HINT = re.compile(r"\b(road|rd\.?|street|cross|layout main)\b", re.I)
_PHASE_HINT = re.compile(r"\b(\d+)(?:st|nd|rd|th)?\s*phase\b", re.I)
_CUISINE_HINT = re.compile(
    r"sandwich|salad|wrap|healthy food|biryani|kebab|barbecue|north indian|south indian|chinese|snacks|street food",
    re.I,
)


def _city_aliases(city: str) -> list[str]:
    token = _fold_place(city)
    if token in {"bangalore", "bengaluru"}:
        return ["bangalore", "bengaluru"]
    if token in {"mangalore", "mangaluru"}:
        return ["mangalore", "mangaluru"]
    return [token] if token else []


def suggestion_head(text: str, city: str = "") -> tuple[str, str]:
    folded = _fold_place(text)
    cut = len(folded)
    for alias in _city_aliases(city) or ["bangalore", "bengaluru"]:
        index = folded.find(alias)
        if index >= 0:
            cut = min(cut, index)
    return folded[:cut].strip(" ,"), folded[cut:].strip()


def is_top_level_locality_match(text: str, locality: str, city: str = "") -> bool:
    """True for parent locality + city, e.g. J. P. Nagar + Bengaluru, not 7th Phase."""
    if rank_location_suggestion(text, f"{locality}, {city}", locality=locality, city=city) is None:
        return False
    loc = _fold_place(locality)
    if not loc:
        return bool(city) and _city_in_place(_fold_place(text), city)
    head, _rest = suggestion_head(text, city)
    if _place_key(head) != _place_key(loc):
        return False
    if city and not _city_in_place(_fold_place(text), city):
        return False
    return True


def choose_location_suggestion(
    candidates: list[str],
    query: str,
    *,
    locality: str = "",
    city: str = "",
    state: str = "",
) -> str:
    """First exact/top-level match in list order; otherwise best remaining score."""
    seen: list[str] = []
    for raw in candidates:
        text = re.sub(r"\s+", " ", (raw or "").strip())
        if text and text not in seen:
            seen.append(text)
    for text in seen:
        if is_top_level_locality_match(text, locality, city):
            return text
    best = ""
    best_score = -999
    for text in seen:
        score = rank_location_suggestion(text, query, locality=locality, city=city, state=state)
        if score is None:
            continue
        if score > best_score:
            best_score = score
            best = text
    return best


def rank_location_suggestion(
    text: str,
    query: str,
    *,
    locality: str = "",
    city: str = "",
    state: str = "",
) -> int | None:
    """Score a platform location suggestion. None means do not click it."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw or len(raw) > 180:
        return None
    hay = _fold_place(raw)
    if _CUISINE_HINT.search(raw):
        return None
    if _RESTAURANT_HINT.search(raw):
        return None
    loc = _fold_place(locality)
    city_token = _fold_place(city)
    if _ROAD_HINT.search(raw) and "road" not in loc and "street" not in loc:
        return None
    phase = _PHASE_HINT.search(raw)
    if phase and "phase" not in loc:
        return None
    if loc and not _locality_in_place(hay, loc):
        return None
    if city_token and not _city_in_place(hay, city_token) and loc and not _locality_in_place(hay, loc):
        return None
    if city_token and not loc and not _city_in_place(hay, city_token):
        return None
    score = suggestion_score(raw, query)
    if loc and _locality_in_place(hay, loc):
        score += 6
    if city_token and _city_in_place(hay, city_token):
        score += 4
    if state and _fold_place(state) in hay:
        score += 2
    if "," in raw:
        score += 1
    if loc and hay.strip() in {loc, f"{loc} {_fold_place(city)}".strip()}:
        score += 3
    head, _rest = suggestion_head(raw, city_token)
    if loc and _place_key(head) == _place_key(loc):
        score += 20
    return score if score > 0 else None


def location_mismatch_message(requested: str, selected: str, url: str = "") -> str:
    return (
        "Location selection failed. "
        f"Requested: {requested}. "
        f"Selected: {selected or '(none)'}. "
        f"Final URL: {url or '(unknown)'}. "
        "Discovery stopped because the selected location is not consistent with the request."
    )


class LocationSelectionError(ValueError):
    pass


def suggestion_score(text: str, query: str) -> int:
    hay = re.sub(r"\s+", " ", (text or "").strip().lower())
    return sum(1 for token in query_tokens(query) if token in hay)


def match_location_suggestion(html: str, query: str) -> str | None:
    try:
        parsed = parse_location(query)
    except ValueError:
        parsed = None
    best = None
    best_score = -1
    blob = html or ""
    for match in SUGGESTION_RE.finditer(blob):
        text = re.sub(r"\s+", " ", match.group(1)).strip()
        score = rank_location_suggestion(
            text,
            query,
            locality=parsed.locality if parsed else "",
            city=parsed.city if parsed else "",
            state=parsed.state if parsed else "",
        )
        if score is None:
            continue
        if score > best_score:
            best_score = score
            best = text
    return best


def magicpin_category_label(kind: CatalogueKind, dining: str = "budget") -> str:
    if kind == "restaurant":
        return "Food Delivery"
    return "Fine Dining" if dining == "fine" else "Budget Dining"


def category_follow_url(html: str, base_url: str, platform: str, kind: CatalogueKind, dining: str = "budget") -> str | None:
    blob = html or ""
    if platform == "magicpin":
        key = "restaurant" if kind == "restaurant" else ("fine" if dining == "fine" else "budget")
        needles = MAGICPIN_ALT[key]
        for href, alt in DISCOVERY_IMG_RE.findall(blob):
            hay = (alt or "").lower()
            if any(needle in hay for needle in needles):
                return join_url(base_url, href)
    labels = [magicpin_category_label(kind, dining)] if platform == "magicpin" else list(CATEGORY_LABELS.get((platform, kind), ()))
    if platform == "magicpin" and dining == "all" and kind == "dineout":
        labels = ["Budget Dining", "Fine Dining"]
    for label in labels:
        pattern = re.compile(
            rf"""<a\b[^>]*href=["']([^"']+)["'][^>]*>\s*{re.escape(label)}\s*</a>""",
            re.I,
        )
        match = pattern.search(blob)
        if match:
            return join_url(base_url, match.group(1))
        loose = re.compile(
            rf"""<a\b[^>]*href=["']([^"']+)["'][^>]*>[\s\S]{{0,240}}?{re.escape(label)}""",
            re.I,
        )
        match = loose.search(blob)
        if match:
            href = match.group(1)
            if platform == "swiggy" and kind == "restaurant" and "dineout" in href.lower():
                continue
            if platform == "swiggy" and kind == "dineout" and "restaurant" in href.lower() and "dineout" not in href.lower():
                continue
            return join_url(base_url, href)
    return None


def locate_script_args(platform: str, kind: CatalogueKind, location: LocationQuery, dining: str = "budget") -> dict[str, str]:
    if platform == "magicpin":
        category = magicpin_category_label(kind, dining)
    else:
        category = CATEGORY_LABELS.get((platform, kind), ("",))[0]
    return {
        "platform": platform,
        "query": picker_query(location),
        "type": type_query(location),
        "category": category,
        "city": location.city or "",
        "state": location.state or "",
        "locality": location.locality or "",
    }
