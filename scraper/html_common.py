from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any
from urllib.parse import urljoin

IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
ATTR_RE = re.compile(r"""(\w+)\s*=\s*["']([^"']+)["']""", re.I)
JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
META_RE = re.compile(
    r'<meta\b[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)

DISCOVERY_HINTS = (
    "similar restaurant",
    "similar restaurants",
    "nearby restaurant",
    "more restaurants",
    "explore other",
    "brands near",
    "people also",
    "people who viewed",
    "sponsored deals",
    "related to",
    "searches leading",
    "people who viewed these also viewed",
    "industrial learning",
    "electronics repair",
)


def strip_tags(html: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", "\n", html or "", flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "\n", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html_lib.unescape(text)
    return re.sub(r"[ \t]+", " ", text)


def cut_at_discovery(text: str | None) -> str:
    """Keep only the primary venue copy; drop similar/nearby/sponsored widgets."""
    value = text or ""
    cut = len(value)
    for hint in DISCOVERY_HINTS:
        match = re.search(re.escape(hint), value, re.I)
        if match:
            cut = min(cut, match.start())
    return value[:cut]


def venue_html(html: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", "\n", html or "", flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "\n", text, flags=re.I | re.S)
    heading = re.search(
        r"<(?:h[1-6])\b[^>]*>\s*(?:similar restaurants?|nearby restaurants?|more restaurants|"
        r"explore other|brands near|people also|people who viewed|sponsored deals|related to|"
        r"searches leading|industrial learning|electronics repair)",
        text,
        re.I,
    )
    if heading:
        return text[: heading.start()]
    return text


def primary_text(html: str) -> str:
    return cut_at_discovery(strip_tags(venue_html(html or "")))


def json_ld_nodes(html: str | None, extra: list[Any] | None = None) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for blob in extra or []:
        _collect_ld(blob, nodes)
    if html:
        for match in JSON_LD_RE.findall(html):
            try:
                parsed = json.loads(match)
            except json.JSONDecodeError:
                continue
            _collect_ld(parsed, nodes)
    return nodes


def _collect_ld(value: Any, nodes: list[dict[str, Any]]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_ld(item, nodes)
        return
    if not isinstance(value, dict):
        return
    nodes.append(value)
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            _collect_ld(item, nodes)


def restaurant_json_ld(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for node in nodes:
        types = node.get("@type")
        names = types if isinstance(types, list) else [types]
        if any(str(name).lower() == "restaurant" for name in names if name):
            return node
    return None


def meta_content(html: str | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if not html:
        return values
    for name, content in META_RE.findall(html):
        values[name.lower()] = content
    return values


def first_h1(html: str | None) -> str | None:
    if not html:
        return None
    match = H1_RE.search(html)
    if not match:
        return None
    text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return text or None


def html_images(html: str | None, base_url: str = "") -> list[dict[str, str]]:
    if not html:
        return []
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for tag in IMG_RE.findall(html):
        attrs = {key.lower(): value for key, value in ATTR_RE.findall(tag)}
        src = attrs.get("src") or attrs.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        if src.startswith("/") and base_url:
            src = urljoin(base_url, src)
        if src in seen or not src.startswith("http"):
            continue
        seen.add(src)
        images.append({"url": src, "alt": attrs.get("alt") or "", "className": attrs.get("class") or ""})
    return images


def looks_like_ui_asset(url: str) -> bool:
    lowered = url.lower()
    return any(
        hint in lowered
        for hint in (
            "logo",
            "sprite",
            "placeholder",
            "favicon",
            "web_assets",
            "icon",
            "pixel",
            "tracking",
            "hamburger",
            "rating-summary",
            "laurel",
        )
    )


def split_cuisines(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return list(dict.fromkeys(parts))
    if not value:
        return []
    parts = [part.strip() for part in re.split(r"[,|/]", str(value)) if part.strip()]
    return list(dict.fromkeys(parts))


MAPS_Q_RE = re.compile(
    r"https://(?:www\.)?google\.com/maps\?q=([-\d.]+),([-\d.]+)",
    re.I,
)


def google_maps_url(html: str | None, text: str | None = None) -> str | None:
    blob = "\n".join(part for part in (html or "", text or "") if part)
    match = MAPS_Q_RE.search(blob)
    if match:
        return f"https://www.google.com/maps?q={match.group(1)},{match.group(2)}"
    return None


VIDEO_TAG_SRC_RE = re.compile(
    r"""<(?:video|source)\b[^>]*src=["']([^"']+)["']""",
    re.I,
)
VIDEO_POSTER_RE = re.compile(
    r"""<video\b[^>]*poster=["']([^"']+)["']""",
    re.I,
)
VIDEO_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+(?:\.(?:mp4|webm|mov|m3u8)|/videos/)[^\s\"'<>]*",
    re.I,
)
OG_VIDEO_RE = re.compile(
    r'<meta[^>]+property=["\']og:video(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)


def extract_venue_videos(html: str | None) -> list[dict[str, Any]]:
    if not html:
        return []
    posters = [match.group(1) for match in VIDEO_POSTER_RE.finditer(html)]
    found: list[dict[str, Any]] = []
    for match in VIDEO_TAG_SRC_RE.finditer(html):
        url = match.group(1).strip()
        if url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            continue
        found.append({"source_url": url, "thumbnail": posters[0] if posters else None})
    for match in OG_VIDEO_RE.finditer(html):
        found.append({"source_url": match.group(1)})
    for url in VIDEO_URL_RE.findall(html):
        if url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            continue
        found.append({"source_url": url})
    return dedupe_videos(found)


def dedupe_videos(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("source_url") or item.get("url") or "").strip()
        key = url.split("?")[0].lower()
        if not url or key in seen:
            continue
        seen.add(key)
        entry = {"source_url": url}
        for field in ("thumbnail", "title"):
            value = item.get(field)
            if value:
                entry[field] = value
        unique.append(entry)
    return unique
