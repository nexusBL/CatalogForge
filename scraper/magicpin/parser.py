from __future__ import annotations

import re
from typing import Any

from scraper.discovery.fields import platform_url_fields
from scraper.html_common import (
    cut_at_discovery,
    dedupe_videos,
    extract_venue_videos,
    first_h1,
    google_maps_url,
    html_images,
    json_ld_nodes,
    looks_like_ui_asset,
    meta_content,
    primary_text,
    restaurant_json_ld,
    split_cuisines,
    strip_tags,
    venue_html,
)
from scraper.platform_dom import (
    MAGICPIN_SIDEBAR_RE,
    categories_from_dom_menu,
    expose_media_urls,
    fill_item_images_from_html,
    is_dish_image,
    merge_category_items,
    merge_item_images,
    unwrap_image_url,
)
from scraper.swiggy.models import Catalogue, DineoutVenue, ExtractionMeta, MenuCategory, MenuItem, RawSource, Restaurant

COST_RE = re.compile(r"₹\s*[\d,]+(?:\.\d+)?\s*for two", re.I)
RATING_RE = re.compile(r"\b([1-5](?:\.\d)?)\s*(?:\((\d[\d,]*)(?:\s+ratings)?\)|(\d[\d,]*)\s+ratings)", re.I)
PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,}\d")
HOURS_RE = re.compile(r"\d{1,2}:\d{2}\s*[AP]M\s*[–-]\s*\d{1,2}:\d{2}\s*[AP]M", re.I)
STORE_URL_RE = re.compile(r"(https?://(?:www\.)?magicpin\.in/.+?/store/[A-Za-z0-9]+)", re.I)
PHOTO_CDN_RE = re.compile(r"magicpin|mpcdn|cloudinary|im1\.magicpin|googleusercontent", re.I)
GOOGLE_PHOTO_RE = re.compile(
    r"https://lh3\.googleusercontent\.com/[A-Za-z0-9_\-]+(?:=[whs]\d+[^\"'\s]*)?",
    re.I,
)

AMENITY_HINTS = (
    "smoking zone",
    "wifi",
    "wheel chair seating",
    "wheel chair accessible entrance and exit",
    "indoor seating",
    "outdoor seating",
    "finger food",
    "serves alcohol",
    "serves beer",
    "seating available",
    "takeaway available",
)


def _html_with_src(html: str) -> str:
    return expose_media_urls(html)


def parse_magicpin_catalogue(raw: RawSource) -> Catalogue:
    if (raw.access_status or ("blocked" if raw.blocked else None)) == "blocked":
        return _empty(raw, "blocked", raw.reason or "Magicpin blocked access to the restaurant page.")

    html = raw.html or ""
    text = "\n".join(
        part for part in (primary_text(_html_with_src(html)), cut_at_discovery(raw.page_text)) if part
    )
    info = restaurant_json_ld(json_ld_nodes(html, raw.json_ld)) or {}
    meta = meta_content(html)
    name = _first(info.get("name"), first_h1(html), _og_name(meta))
    address = _address(info, text)
    locality = _locality(text, address)
    cuisines = split_cuisines(info.get("servesCuisine")) or _cuisines(text)
    rating, rating_count = _rating(text, info)
    price = _first(info.get("priceRange"), _search(COST_RE, text))
    hours = info.get("openingHours")
    if isinstance(hours, list):
        hours = "; ".join(str(item) for item in hours if item)
    hours = _first(hours, _search(HOURS_RE, text))
    status = "Open now" if re.search(r"open now", text, re.I) else None
    phone = _phone(info.get("telephone") or "", text)
    images = _images(raw, html, info, meta)
    gallery = [item for item in images if item.get("category") != "menu"]
    menu_images = [item["url"] for item in images if item.get("category") == "menu"]
    hero = gallery[0]["url"] if gallery else (images[0]["url"] if images else None)
    offers = _offers(text)
    amenities = _amenities(text)
    restaurant_id = _store_id(raw.source_url)
    menu_source = (raw.page_text or "").strip() or strip_tags(expose_media_urls(html))
    text_menu = _menu_from_delivery(menu_source, html)
    harvested = categories_from_dom_menu(raw.dom_menu)
    categories = harvested or text_menu or _menu_categories(raw.api_payloads, menu_source, html)
    if harvested and text_menu:
        merge_category_items(categories, text_menu)
        merge_item_images(categories, text_menu)
    fill_item_images_from_html(categories, html)
    menu_pages = [{"title": "Menu", "images": menu_images}] if menu_images else []

    restaurant = Restaurant(
        name=name,
        rating=rating,
        rating_count=rating_count,
        price_for_two=price,
        cuisines=cuisines,
        outlet=locality,
        address=address,
        image_url=hero,
        offers=offers,
        phone=phone,
        opening_hours=hours,
        opening_status=status,
        restaurant_id=restaurant_id,
        additional_information={"platform": "magicpin"},
        magicpin_rating=rating,
        magicpin_url=platform_url_fields(raw.source_url)["magicpin_url"],
    )
    maps = google_maps_url(html, text)
    venue = DineoutVenue(
        venue=name,
        restaurant_id=restaurant_id,
        hero_image=hero,
        rating=rating,
        rating_count=rating_count,
        cuisines=cuisines,
        price_for_two=price,
        opening_hours=hours,
        opening_status=status,
        phone=phone,
        offers=offers,
        menu_pages=menu_pages,
        photos=[item["url"] for item in gallery],
        gallery_images=gallery,
        videos=extract_venue_videos(html),
        amenities=amenities,
        location={"address": address, "locality": locality, "maps_url": maps},
        directions_url=maps,
        source_url=raw.source_url,
        actions={"call": phone or "", "directions": maps or ""},
    )
    has_data = bool(name or images or offers or address)
    items = [item for category in categories for item in category.items]
    dish_images = sum(1 for item in items if item.image_url)
    image_count = dish_images if items else len(images)
    return Catalogue(
        source="magicpin",
        source_url=raw.source_url,
        extraction_status="ok" if has_data else "failed",
        source_type="dom",
        restaurant=restaurant,
        dineout=venue if has_data else None,
        categories=categories,
        item_count=len(items),
        image_count=image_count,
        error=None if has_data else (raw.reason or "Page was reachable but no Magicpin venue data was found."),
        extraction=ExtractionMeta(
            ok=has_data,
            blocked=False,
            extraction_status="ok" if has_data else "failed",
            source_type="dom",
            http_status=raw.http_status,
            data_locations=list(raw.data_locations or []),
        ),
    )


def photos_gallery_url(url: str) -> str | None:
    """The '+76 Photos' control opens /store/{id}/photos?img=photos&id=1."""
    match = STORE_URL_RE.search(url or "")
    if not match:
        return None
    base = match.group(1).rstrip("/")
    path = (url or "").split("?")[0].rstrip("/").lower()
    if path.endswith("/photos"):
        return None
    return f"{base}/photos?img=photos&id=1"


def delivery_menu_url(url: str) -> str | None:
    """Delivery tab: {store}/delivery — category sidebar plus priced dish cards."""
    match = STORE_URL_RE.search(url or "")
    if not match:
        return None
    base = match.group(1).rstrip("/")
    path = (url or "").split("?")[0].rstrip("/").lower()
    if path.endswith("/delivery") or path.endswith("/menu"):
        return None
    return f"{base}/delivery"


def merge_magicpin_menu(base: Catalogue, extra: Catalogue) -> Catalogue:
    if extra.extraction_status != "ok" or not extra.categories:
        return base
    extra_score = (
        sum(1 for category in extra.categories for item in category.items if item.image_url),
        extra.item_count,
        len(extra.categories),
    )
    base_score = (
        sum(1 for category in base.categories for item in category.items if item.image_url),
        base.item_count,
        len(base.categories),
    )
    if extra_score < base_score:
        return base
    base.categories = extra.categories
    base.item_count = extra.item_count
    base.image_count = extra_score[0]
    return base


def merge_magicpin_images(base: Catalogue, extra: Catalogue) -> Catalogue:
    if extra.extraction_status != "ok" or not extra.dineout:
        return base
    existing = list(base.dineout.gallery_images if base.dineout else []) + [
        {"url": url, "category": "menu"}
        for page in (base.dineout.menu_pages if base.dineout else [])
        for url in (page.get("images") or [])
    ]
    extra_images = list(extra.dineout.gallery_images or []) + [
        {"url": url, "category": "menu"}
        for page in (extra.dineout.menu_pages or [])
        for url in (page.get("images") or [])
    ]
    merged = _dedupe_images([*existing, *extra_images])
    gallery = [item for item in merged if item.get("category") != "menu"]
    menu_images = [item["url"] for item in merged if item.get("category") == "menu"]
    hero = gallery[0]["url"] if gallery else (merged[0]["url"] if merged else None)
    if base.restaurant:
        base.restaurant.image_url = base.restaurant.image_url or hero
    if base.dineout:
        base.dineout.hero_image = base.dineout.hero_image or hero
        base.dineout.gallery_images = gallery
        base.dineout.photos = [item["url"] for item in gallery]
        extra_videos = extra.dineout.videos if extra.dineout else []
        base.dineout.videos = dedupe_videos([*(base.dineout.videos or []), *(extra_videos or [])])
        if menu_images:
            pages = list(base.dineout.menu_pages or [])
            if pages:
                pages[0]["images"] = list(dict.fromkeys([*(pages[0].get("images") or []), *menu_images]))
            else:
                pages = [{"title": "Menu", "images": menu_images}]
            base.dineout.menu_pages = pages
    dish_images = sum(1 for category in base.categories for item in category.items if item.image_url)
    base.image_count = dish_images if base.item_count else len(merged)
    return base


def _empty(raw: RawSource, status: str, error: str) -> Catalogue:
    return Catalogue(
        source="magicpin",
        source_url=raw.source_url,
        extraction_status=status,
        error=error,
        extraction=ExtractionMeta(ok=False, blocked=status == "blocked", extraction_status=status, error=error),
    )


def _first(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value not in (None, "", [], {}):
            return value
    return None


def _og_name(meta: dict[str, str]) -> str | None:
    title = meta.get("og:title") or meta.get("twitter:title") or ""
    if not title:
        return None
    return title.split("|")[0].split("-")[0].strip() or None


def _address(info: dict[str, Any], text: str) -> str | None:
    addr = info.get("address")
    if isinstance(addr, str) and addr.strip():
        return addr.strip()
    if isinstance(addr, dict):
        return _first(addr.get("streetAddress"), addr.get("addressLocality"))
    match = re.search(
        r"(Ground Floor[^\n]{10,120}|[\d]+,[^\n]{10,120}Bengaluru[^\n]{0,40})",
        text,
        re.I,
    )
    return match.group(1).strip() if match else None


def _locality(text: str, address: str | None) -> str | None:
    match = re.search(r"([A-Za-z][A-Za-z\s]+),\s*Bangalore", text)
    if match:
        return match.group(0).strip()
    return None


def _cuisines(text: str) -> list[str]:
    for line in text.split("\n"):
        line = line.strip()
        if line.lower() in {"south indian", "north indian", "chinese", "italian", "continental"}:
            return [line]
    return []


def _rating(text: str, info: dict[str, Any]) -> tuple[float | None, str | None]:
    match = RATING_RE.search(text)
    if match:
        try:
            return float(match.group(1)), (match.group(2) or match.group(3) or "").replace(",", "") or None
        except ValueError:
            pass
    rating = info.get("aggregateRating")
    if isinstance(rating, dict):
        try:
            return float(rating.get("ratingValue")), str(rating.get("ratingCount") or "") or None
        except (TypeError, ValueError):
            return None, None
    return None, None


def _search(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def _phone(ld_phone: str, text: str) -> str | None:
    if ld_phone.strip():
        return ld_phone.strip()
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else None


def _images(raw: RawSource, html: str, info: dict[str, Any], meta: dict[str, str]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []

    def add(url: str | None, category: str = "ambience") -> None:
        if not url or not str(url).startswith("http") or looks_like_ui_asset(url):
            return
        unwrapped = unwrap_image_url(url)
        if not unwrapped or not PHOTO_CDN_RE.search(unwrapped):
            return
        lowered = unwrapped.lower()
        if "/videos/" in lowered or "thumbnail.jpg" in lowered:
            return
        if re.search(r"electronics|insurance|learning.center|footwear|pvr cinemas|laptop.repair|visa online", lowered):
            return
        images.append({"url": unwrapped, "category": category})

    if isinstance(info.get("image"), str):
        add(info.get("image"))
    og = meta.get("og:image")
    if og and og.startswith("http"):
        add(og)
    scoped = venue_html(html)
    for item in html_images(scoped, raw.source_url):
        alt = (item.get("alt") or "").lower()
        if re.search(r"similar|nearby|recommended|more restaurant|footwear|repair|insurance|cinemas|learning|visa online|styling", alt):
            continue
        category = "menu" if "menu" in alt else "food" if "food" in alt else "ambience"
        add(item.get("url"), category)
    for match in GOOGLE_PHOTO_RE.findall(scoped):
        add(match, "ambience")
    for item in raw.dom_images or []:
        if isinstance(item, dict):
            add(item.get("url"))
    return _dedupe_images(images)


def _image_key(url: str) -> str:
    base = url.split("?")[0]
    if "googleusercontent.com" in base.lower():
        return re.sub(r"=[whs]\d+.*$", "", base, flags=re.I).lower()
    return base.lower()


def _image_rank(url: str) -> int:
    match = re.search(r"=[whs](\d+)", url, re.I)
    return int(match.group(1)) if match else 0


def _dedupe_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in images:
        url = item.get("url") or ""
        key = _image_key(url)
        if key not in best:
            best[key] = item
            order.append(key)
            continue
        current = best[key]
        if _image_rank(url) > _image_rank(current.get("url") or ""):
            best[key] = {**current, "url": url}
    return [best[key] for key in order]


def _offers(text: str) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    for match in re.finditer(
        r"(Save\s+\d+%[^\n]{0,40}|\d+%\s+off(?:\s+up to[^.\n]{0,40})?|Flat\s+\d+%\s+OFF|₹\s*[\d,]+\s+OFF)",
        text,
        re.I,
    ):
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(title) > 80:
            continue
        if title.lower() not in {item["title"].lower() for item in offers}:
            offers.append({"title": title, "type": "Dining offer", "description": "Dining / store offer"})
    return offers[:8]


def _amenities(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for hint in AMENITY_HINTS:
        if hint in lowered:
            found.append(hint.title())
    return list(dict.fromkeys(found))


def _store_id(url: str) -> str | None:
    match = re.search(r"/store/([A-Za-z0-9]+)", url)
    return match.group(1) if match else None


CATEGORY_COUNTS_RE = re.compile(r"^(.+?)\s+\((\d+)\)\s*$")
PRICE_RE = re.compile(r"^₹\s*([\d,]+(?:\.\d+)?)$")
ITEM_COUNT_RE = re.compile(r"^\d+\s+items?$", re.I)
VEG_ICON_RE = re.compile(r"magicpin\.in/images/merchant/(veg|non-veg|egg)-icon", re.I)
FOOD_PHOTO_RE = re.compile(r"https://lh3\.googleusercontent\.com/[^\s\"'<>]+", re.I)

DELIVERY_NOISE = {
    "veg",
    "non-veg",
    "non veg",
    "bestsellers",
    "bestseller",
    "spicy",
    "add",
    "customizable",
    "order online",
    "order now",
    "photos",
    "overview",
    "offers",
    "delivery",
    "menu",
    "reviews",
    "pay bill",
    "directions",
    "open now",
    "more",
    "... more",
}

DELIVERY_HEADINGS = {
    "recommended",
    "starters",
    "desserts",
    "beverages",
    "veg biryanis",
    "non veg biryanis",
}


def _clean_markup(value: str) -> str:
    value = re.sub(r"</?customFont[^>]*>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip(" ,")


def _delivery_window(text: str, html: str = "") -> str:
    blob = text or ""
    start_at = None
    for pattern in (
        r'aria-label="Menu categories"',
        r"Recommended\s+\(\d+\)",
        r"Order Online",
    ):
        match = re.search(pattern, blob, re.I)
        if match:
            start_at = match.start() if start_at is None else min(start_at, match.start())
    if start_at is not None:
        blob = blob[start_at:]
    stop = re.search(
        r"more restaurants|people who viewed|searches leading to this page",
        blob,
        re.I,
    )
    if stop:
        blob = blob[: stop.start()]
    return blob


def _menu_categories(payloads: list[Any], text: str, html: str = "") -> list[MenuCategory]:
    items: list[MenuItem] = []
    for payload in payloads:
        items.extend(_items_from_payload(payload))
    if items:
        cleaned = [
            MenuItem(
                name=_clean_markup(item.name),
                price=item.price,
                original_price=item.original_price,
                food_type=item.food_type,
                image_url=item.image_url,
                is_bestseller=item.is_bestseller,
            )
            for item in items
            if _clean_markup(item.name) and "customfont" not in item.name.lower()
        ]
        if cleaned:
            return [MenuCategory(name="Menu", items=cleaned)]
    return _menu_from_delivery(_delivery_window(text, html), html)


def _items_from_payload(value: Any) -> list[MenuItem]:
    found: list[MenuItem] = []
    if isinstance(value, list):
        for item in value:
            found.extend(_items_from_payload(item))
        return found
    if not isinstance(value, dict):
        return found
    name = value.get("name") or value.get("itemName") or value.get("title") or value.get("productName")
    price = value.get("price") or value.get("sellingPrice") or value.get("discountedPrice") or value.get("finalPrice")
    if isinstance(name, str) and name.strip() and price not in (None, "") and "customfont" not in name.lower():
        image = None
        for key in ("imageUrl", "image_url", "image", "mediaUrl", "photo"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith("http"):
                image = candidate
                break
        found.append(
            MenuItem(
                name=name.strip(),
                price=price if isinstance(price, (int, float)) else None,
                image_url=image,
            )
        )
        return found
    for child in value.values():
        found.extend(_items_from_payload(child))
    return found


def _delivery_tokens(text: str) -> list[str]:
    blob = _delivery_window(text)
    blob = FOOD_PHOTO_RE.sub(lambda match: f"\n{match.group(0)}\n", blob)
    blob = re.sub(r"(https://magicpin\.in/images/[^\s\"'<>]+)", r"\n\1\n", blob, flags=re.I)
    blob = re.sub(r"(₹\s*[\d,]+(?:\.\d+)?)", r"\n\1\n", blob)
    blob = re.sub(r"\b(Add)\b", r"\n\1\n", blob)
    tokens: list[str] = []
    for line in blob.splitlines():
        piece = _clean_markup(line)
        if piece:
            tokens.append(piece)
    return tokens


def _sidebar_categories(html: str, text: str) -> list[MenuCategory]:
    categories: list[MenuCategory] = []
    seen: set[str] = set()
    blob = html or text or ""
    for match in re.finditer(
        r'data-mp-delivery-sidebar-section="\d+:([^"]+)"[^>]*>([^<]*)',
        blob,
        re.I,
    ):
        name = _clean_markup(match.group(1))
        counted = CATEGORY_COUNTS_RE.match(_clean_markup(match.group(2)))
        count = int(counted.group(2)) if counted else None
        key = name.lower()
        if not name or key in seen or key in DELIVERY_NOISE:
            continue
        seen.add(key)
        categories.append(MenuCategory(name=name, items=[], item_count=count))
    if categories:
        return categories
    for match in MAGICPIN_SIDEBAR_RE.finditer(blob):
        name = _clean_markup(match.group(1))
        key = name.lower()
        if not name or key in seen or key in DELIVERY_NOISE:
            continue
        seen.add(key)
        categories.append(MenuCategory(name=name, items=[]))
    return categories


def _menu_from_delivery(text: str, html: str = "") -> list[MenuCategory]:
    tokens = _delivery_tokens(text)
    categories = _sidebar_categories(html, text)
    sidebar = {category.name.lower() for category in categories}
    if not categories and not any(
        CATEGORY_COUNTS_RE.match(token) or VEG_ICON_RE.search(token) for token in tokens
    ):
        return []
    current: MenuCategory | None = categories[0] if categories else None
    pending: dict[str, Any] = {}

    def switch(name: str, count: int | None = None) -> None:
        nonlocal current
        key = name.lower()
        for category in categories:
            if category.name.lower() == key:
                current = category
                if count is not None:
                    current.item_count = count
                return
        current = MenuCategory(name=name, items=[], item_count=count)
        categories.append(current)

    def flush() -> None:
        nonlocal pending
        name = _clean_markup(str(pending.get("name") or ""))
        prices = list(pending.get("prices") or [])
        if not name or not prices or "customfont" in name.lower() or name.lower() in DELIVERY_NOISE:
            pending = {}
            return
        if current is None:
            switch("Menu")
        target = current
        if any(existing.name.lower() == name.lower() for existing in target.items):
            pending = {}
            return
        selling = min(prices)
        original = max(prices) if len(prices) > 1 else None
        image = unwrap_image_url(pending.get("image"))
        if image and not is_dish_image(image):
            image = None
        target.items.append(
            MenuItem(
                name=name,
                price=selling,
                original_price=original if original != selling else None,
                food_type=pending.get("food_type"),
                image_url=image,
                source_image_url=image,
                is_bestseller=bool(pending.get("bestseller")),
                description=pending.get("description"),
            )
        )
        pending = {}

    for token in tokens:
        counted = CATEGORY_COUNTS_RE.match(token)
        if counted and 1 <= int(counted.group(2)) <= 200:
            flush()
            switch(_clean_markup(counted.group(1)), int(counted.group(2)))
            continue
        if token.strip().lower() in sidebar:
            flush()
            switch(token.strip())
            continue
        if ITEM_COUNT_RE.match(token):
            continue
        if FOOD_PHOTO_RE.search(token) or token.lower().startswith("http"):
            url = unwrap_image_url(token)
            if is_dish_image(url):
                pending["image"] = url
            continue
        veg = VEG_ICON_RE.search(token)
        if veg:
            pending["food_type"] = veg.group(1)
            continue
        if token.lower() == "bestseller":
            pending["bestseller"] = True
            continue
        if token.lower() in {"customizable", "add"} or "star-" in token.lower() or re.search(r"\bratings?\b", token, re.I):
            if token.lower() == "add":
                flush()
            continue
        price = PRICE_RE.match(token)
        if price:
            amount = float(price.group(1).replace(",", ""))
            pending.setdefault("prices", []).append(int(amount) if amount.is_integer() else amount)
            continue
        lowered = token.lower()
        if lowered in DELIVERY_NOISE or lowered.startswith("lic") or "for two" in lowered:
            continue
        if len(token) > 48 or re.search(r"\b(served|layered|cooked|allergens)\b", token, re.I):
            if pending.get("name") and not pending.get("description"):
                pending["description"] = token
            continue
        if not re.search(r"[A-Za-z]", token) or len(token) < 3:
            continue
        if pending.get("name") and pending.get("prices"):
            flush()
        pending["name"] = token
    flush()
    return categories
