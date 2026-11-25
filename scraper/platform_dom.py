"""Zomato / Magicpin live-menu harvest. Does not change Swiggy collection."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from scraper.swiggy.models import MenuCategory, MenuItem

JUNK_IMAGE_RE = re.compile(
    r"veg-icon|non-veg-icon|egg-icon|star-filled|star-empty|star-|web_assets|web/assets|placeholder|logo|favicon|thumb|=s120\b|=w120\b|sprite|avatar|app-store|play-store|merchant_app|badge|rating_|\/images\/merchant\/|\/images\/icons\/",
    re.I,
)
FOOD_CDN_RE = re.compile(
    r"dish_photos|googleusercontent|magicpin|mpcdn|im1\.magicpin|swiggy|zmtcdn|cloudinary",
    re.I,
)


def unwrap_image_url(url: str | None) -> str | None:
    if not url:
        return None
    text = url.strip()
    match = re.search(r"[?&]url=([^&]+)", text)
    if match:
        inner = unquote(match.group(1))
        if inner.startswith("http"):
            text = inner

    lowered = text.lower()

    # Google User Content (lh3.googleusercontent.com) - upgrade =w200, =w400, =s300, etc. to high-res =s1200
    if "googleusercontent.com" in lowered:
        if not re.search(r"thumb|=w200-rw", lowered):
            text = re.sub(r"=[whs]\d+(?:-[a-z0-9]+)*", "=s1200", text, flags=re.I)

    # Swiggy / Cloudinary - upgrade low-res width limits (w_112, w_208, w_264, w_300, w_508, etc.) to w_1000
    elif "media-assets.swiggy.com" in lowered or "res.cloudinary.com" in lowered:
        text = re.sub(r"\bw_\d+(?:,h_\d+)?[^/]*", "w_1000,f_auto,q_auto", text, flags=re.I)

    # Zomato CDN (b.zmtcdn.com) - remove low-res fit/crop constraints
    elif "zmtcdn.com" in lowered:
        text = re.sub(r"[?&]fit=around(?:%7c|\|)\d+[^&]*", "", text, flags=re.I)
        text = re.sub(r"[?&]crop=\d+[^&]*", "", text, flags=re.I)
        text = text.rstrip("?&")

    # Magicpin CDN (im1.magicpin.com / mpcdn.in)
    elif "mpcdn" in lowered or "magicpin.com" in lowered:
        text = re.sub(r"tr=w-\d+(?:,h-\d+)?", "tr=w-1000", text, flags=re.I)

    return text


def is_dish_image(url: str | None) -> bool:
    if not url or not str(url).startswith("http"):
        return False
    lowered = str(url).lower()
    if JUNK_IMAGE_RE.search(lowered) or "=w200-rw" in lowered or re.search(r"=[sw]120\b", lowered):
        return False
    text = unwrap_image_url(url)
    if not text:
        return False
    text_lowered = text.lower()
    if FOOD_CDN_RE.search(text_lowered):
        return True
    if re.search(r"\.(jpg|jpeg|png|webp|avif)($|\?)", text_lowered) and not re.search(r"icon|logo|avatar|button|badge|rating_", text_lowered):
        return True
    return False


def debug_item_image(categories: list[MenuCategory], name: str) -> dict[str, Any] | None:
    needle = name.lower()
    for category in categories:
        for item in category.items:
            if item.name.lower() != needle:
                continue
            candidates = [value for value in (item.image_url, item.source_image_url) if value]
            return {
                "category": category.name,
                "name": item.name,
                "price": item.price,
                "image_candidates": candidates,
                "image_url": item.image_url,
                "source_image_url": item.source_image_url,
            }
    return None


def _normalize_item_name(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().lower()


def fill_item_images_from_html(categories: list[MenuCategory], html: str) -> None:
    item_names = {_normalize_item_name(item.name) for category in categories for item in category.items}
    labeled: dict[str, str] = {}
    blob = html or ""
    for tag in re.findall(r"<img\b[^>]*>", blob, flags=re.I):
        attrs = {key.lower(): value for key, value in re.findall(r"""(\w+)\s*=\s*["']([^"']+)["']""", tag)}
        candidates = [
            unwrap_image_url(attrs.get("src")),
            unwrap_image_url(attrs.get("data-src")),
            unwrap_image_url(attrs.get("data-original")),
            unwrap_image_url(attrs.get("data-lazy-src")),
        ]
        srcset = attrs.get("srcset") or attrs.get("data-srcset") or ""
        parts = [part.strip().split(" ")[0] for part in srcset.split(",") if part.strip()]
        if parts:
            candidates.append(unwrap_image_url(parts[-1]))
        url = next((item for item in candidates if item and is_dish_image(item)), None)
        alt = _normalize_item_name(attrs.get("alt") or "")
        if alt and url and alt in item_names:
            labeled[alt] = url
    for match in STYLE_URL_RE.finditer(blob):
        url = unwrap_image_url(match.group(2))
        if not is_dish_image(url):
            continue
        window = blob[max(0, match.start() - 500) : match.start()]
        titles = re.findall(r">([^<]{3,80})<", window)
        for title in reversed(titles):
            name = _normalize_item_name(title)
            if name in item_names:
                labeled.setdefault(name, url)
                break
    for category in categories:
        for item in category.items:
            current = unwrap_image_url(item.image_url)
            if is_dish_image(current):
                item.image_url = current
                item.source_image_url = unwrap_image_url(item.source_image_url) or current
                continue
            item.image_url = None
            item.source_image_url = None
            key = _normalize_item_name(item.name)
            if key in labeled:
                item.image_url = labeled[key]
                item.source_image_url = labeled[key]


def merge_item_images(primary: list[MenuCategory], secondary: list[MenuCategory]) -> None:
    by_name: dict[str, MenuItem] = {}
    for category in secondary:
        for item in category.items:
            by_name[item.name.lower()] = item
    for category in primary:
        for item in category.items:
            if is_dish_image(item.image_url):
                continue
            other = by_name.get(item.name.lower())
            if other and is_dish_image(other.image_url):
                item.image_url = other.image_url
                item.source_image_url = other.source_image_url or other.image_url


def merge_category_items(primary: list[MenuCategory], secondary: list[MenuCategory]) -> None:
    """Keep harvested sidebar order; take dish membership from the sequential parser when it has that section."""
    by_name = {category.name.lower(): category for category in secondary}
    images: dict[str, MenuItem] = {}
    for category in primary:
        for item in category.items:
            if is_dish_image(item.image_url):
                images[item.name.lower()] = item
    for category in primary:
        other = by_name.get(category.name.lower())
        if other and other.items:
            category.items = list(other.items)
            if category.item_count is None:
                category.item_count = other.item_count
        for item in category.items:
            source = images.get(item.name.lower())
            if source and not is_dish_image(item.image_url):
                item.image_url = source.image_url
                item.source_image_url = source.source_image_url or source.image_url


MAGICPIN_SIDEBAR_RE = re.compile(
    r'data-mp-delivery-sidebar-section="\d+:([^"]+)"',
    re.I,
)
ZOMATO_DISH_RE = re.compile(
    r"https://b\.zmtcdn\.com/data/dish_photos/[^\s\"'<>)]+",
    re.I,
)
MAGICPIN_FOOD_RE = re.compile(
    r"https://lh3\.googleusercontent\.com/[^\s\"'<>)]+",
    re.I,
)
SRCSET_RE = re.compile(r"""(?:srcset|data-srcset)\s*=\s*["']([^"']+)["']""", re.I)
STYLE_URL_RE = re.compile(r"""url\((["']?)(https?:[^"')]+)\1\)""", re.I)

MAGICPIN_WAIT = """() => Boolean(
    document.querySelector('[data-mp-delivery-sidebar-section], nav[aria-label="Menu categories"]')
)"""
ZOMATO_WAIT = """() => {
    const html = document.documentElement ? document.documentElement.innerHTML : '';
    return html.includes('dish_photos') || /Search within menu/i.test(document.body ? document.body.innerText : '');
}"""

_HARVEST_PATH = Path(__file__).with_name("platform_menu_harvest.js")
HARVEST_JS = _HARVEST_PATH.read_text(encoding="utf-8")


def platform_from_url(url: str | None) -> str | None:
    host = urlparse(url or "").netloc.lower()
    if "zomato" in host:
        return "zomato"
    if "magicpin" in host:
        return "magicpin"
    return None


def wait_for_platform_menu(page, url: str | None) -> None:
    platform = platform_from_url(url or getattr(page, "url", "") or "")
    if not platform:
        return
    path = (url or getattr(page, "url", "") or "").split("?")[0].lower()
    if "/photos" in path:
        return
    try:
        if platform == "magicpin":
            clicked = _click_if_present(page, "a[href*='/delivery'], [href*='/delivery?'], [href*='tabType=delivery']")
            if not clicked:
                try:
                    page.get_by_role("tab", name=re.compile(r"delivery", re.I)).click(timeout=1500)
                    clicked = True
                except Exception:
                    pass
            if not clicked:
                try:
                    page.get_by_text("Delivery", exact=True).click(timeout=1500)
                    clicked = True
                except Exception:
                    pass
            page.wait_for_function(MAGICPIN_WAIT, timeout=12_000)
        else:
            _click_if_present(page, "a[href*='/order']")
            page.wait_for_function(ZOMATO_WAIT, timeout=12_000)
        page.wait_for_timeout(400)
    except Exception:
        pass


def harvest_platform_menu(page, url: str | None) -> dict[str, Any]:
    if not platform_from_url(url or getattr(page, "url", "") or ""):
        return {}
    try:
        payload = page.evaluate(HARVEST_JS)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def categories_from_dom_menu(dom_menu: list[Any] | None) -> list[MenuCategory]:
    categories: list[MenuCategory] = []
    for block in dom_menu or []:
        if not isinstance(block, dict):
            continue
        raw_name = str(block.get("name") or "").strip()
        if raw_name and (re.match(r"^\d+(\.\d+)?$", raw_name) or raw_name.lower() in {"overview", "offers", "delivery", "dineout", "menu", "reviews", "photos", "order online", "search"}):
            raw_name = ""
        name = raw_name or "Menu"
        items: list[MenuItem] = []
        for raw in block.get("items") or []:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            prices = [value for value in (raw.get("price"), raw.get("original_price")) if isinstance(value, (int, float))]
            selling = min(prices) if prices else raw.get("price")
            original = max(prices) if len(prices) > 1 else raw.get("original_price")
            url = raw.get("image_url") if isinstance(raw.get("image_url"), str) else None
            if url and not is_dish_image(url):
                url = None
            items.append(
                MenuItem(
                    name=str(raw["name"]).strip(),
                    description=raw.get("description") if isinstance(raw.get("description"), str) else None,
                    price=selling if isinstance(selling, (int, float)) else None,
                    original_price=original if isinstance(original, (int, float)) and original != selling else None,
                    image_url=url,
                    source_image_url=url,
                    food_type=raw.get("food_type") if isinstance(raw.get("food_type"), str) else None,
                    is_bestseller=bool(raw.get("is_bestseller")),
                )
            )
        count = block.get("item_count")
        item_count = int(count) if isinstance(count, (int, float)) else (len(items) or None)
        if items or item_count:
            categories.append(MenuCategory(name=name, items=items, item_count=item_count))
    return categories


def menu_from_magicpin_html(html: str) -> list[MenuCategory]:
    names = [item.strip() for item in MAGICPIN_SIDEBAR_RE.findall(html or "") if item.strip()]
    if not names:
        return []
    categories = [MenuCategory(name=name, items=[]) for name in dict.fromkeys(names)]
    current = categories[0]
    # Pair nearby food images with nearby headings when the live card HTML is present.
    for match in re.finditer(
        r'data-mp-delivery-sidebar-section="\d+:([^"]+)"[\s\S]{0,4000}?(https://lh3\.googleusercontent\.com/[^"\s]+)',
        html or "",
        re.I,
    ):
        pass
    return [category for category in categories if category.items] or []


def expose_media_urls(html: str) -> str:
    """Keep img/srcset/background URLs in document order for text parsers."""
    text = html or ""

    def replace_img(tag: str) -> str:
        urls: list[str] = []
        src = re.search(
            r"""(?:src|data-src|data-original|data-lazy-src)\s*=\s*["']([^"']+)["']""",
            tag,
            re.I,
        )
        if src and src.group(1).startswith("http"):
            urls.append(src.group(1))
        srcset = SRCSET_RE.search(tag)
        if srcset:
            parts = [part.strip().split(" ")[0] for part in srcset.group(1).split(",") if part.strip()]
            if parts and parts[-1].startswith("http"):
                urls.append(parts[-1])
        return "\n" + "\n".join(urls) + "\n" if urls else tag

    text = re.sub(r"<img\b[^>]*>", lambda match: replace_img(match.group(0)), text, flags=re.I)
    text = STYLE_URL_RE.sub(lambda match: f"\n{match.group(2)}\n", text)
    return text


def _click_if_present(page, selector: str) -> None:
    try:
        loc = page.locator(selector)
        if loc.count() == 0:
            return
        loc.first.click(timeout=2_000)
        page.wait_for_timeout(500)
    except Exception:
        pass
