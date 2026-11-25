"""Zomato adapter.

identity: schema.org Restaurant JSON-LD (name, address, phone, priceRange, openingHours, geo, image)
menu: Order Online DOM text (categories then dishes); XHR payloads when captured
offers: Dining Offers headings on the primary venue page
photos: b.zmtcdn.com/data/pictures/{id}/ on the primary venue; skip web_assets and similar restaurants
location: JSON-LD address + geo/hasmap
dineout: Overview tab dining rating, offers, amenities, menu page counts — not Similar restaurants
"""

from __future__ import annotations

import re
from typing import Any

from scraper.discovery.fields import is_distance_text, platform_url_fields
from scraper.html_common import (
    first_h1,
    google_maps_url,
    html_images,
    cut_at_discovery,
    dedupe_videos,
    extract_venue_videos,
    json_ld_nodes,
    looks_like_ui_asset,
    meta_content,
    primary_text,
    restaurant_json_ld,
    split_cuisines,
    venue_html,
)
from scraper.platform_dom import categories_from_dom_menu, expose_media_urls, fill_item_images_from_html, merge_category_items, merge_item_images
from scraper.swiggy.models import Catalogue, DineoutVenue, ExtractionMeta, MenuCategory, MenuItem, RawSource, Restaurant

ZOMATO_ASSET = re.compile(r"zmtcdn\.com/data/", re.I)
RES_ID_RE = re.compile(r"/data/pictures/\d+/(\d+)/", re.I)
DINING_RE = re.compile(
    r"([\d.]+)\s+(\d[\d,]*)\s+Dining Ratings\s+([\d.]+|-)\s+(\d[\d,]*|-)\s+Delivery Ratings",
    re.I,
)
PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,}\d")
COST_RE = re.compile(r"(₹[\d,]+(?:\.\d+)?\s*for two[^\n]*)", re.I)
MENU_SECTION_RE = re.compile(r"(Food Menu|Bar Menu|Breakfast Menu)\s+(\d+)\s+pages?", re.I)
CATEGORY_COUNTS_RE = re.compile(r"^(.+?)\s+\((\d+)\)\s*$")
DISH_PHOTO_RE = re.compile(r"https://b\.zmtcdn\.com/data/dish_photos/[^\s\"'<>]+", re.I)
RELATED_CUT_RE = re.compile(r"\bRELATED TO\b|\bSimilar restaurants\b|\bExplore other\b", re.I)
ZOMATO_TAB_RE = re.compile(r"(https?://(?:www\.)?zomato\.com/[^?#]+)", re.I)
AMENITY_HINTS = (
    "indoor seating",
    "outdoor seating",
    "bar seating",
    "takeaway available",
    "full bar available",
    "smoking area",
    "garden",
    "nightlife",
    "cocktails",
    "wifi",
    "parking",
    "live music",
    "wheelchair",
)

MENU_NOISE = {
    "order online",
    "search",
    "cross",
    "search within menu",
    "explore",
    "live track your order",
    "download the app",
    "currently closed for online ordering",
    "online ordering is only supported on the mobile app",
    "view gallery",
    "book a table",
    "open now",
    "dining ratings",
    "delivery ratings",
    "direction",
    "share",
    "reviews",
    "call",
    "info-line",
    "direction-line",
    "chevron-right",
    "star-fill",
    "time",
    "photos",
    "overview",
    "menu",
    "read more",
    "add",
}

CUISINE_ONLY = {
    "biryani",
    "kebab",
    "chinese",
    "bbq",
    "north indian",
    "south indian",
    "bar food",
    "italian",
    "continental",
    "mughlai",
    "andhra",
    "hyderabadi",
    "desserts",
    "briyani",
}

MENU_HEADINGS = (
    "tandoor",
    "main course",
    "starters",
    "11’’ pizza",
    "11'' pizza",
    "accompaniments",
    "desserts",
    "beverages",
    "soups",
    "salads",
    "breads",
    "burgers",
    "breakfast",
    "bar bites",
    "egg special",
    "indian breads",
    "sides / extra",
    "sides",
)


def _html_with_src(html: str) -> str:
    return expose_media_urls(html)


def parse_zomato_catalogue(raw: RawSource) -> Catalogue:
    if (raw.access_status or ("blocked" if raw.blocked else None)) == "blocked":
        return _empty(raw, "blocked", raw.reason or "Zomato blocked access to the restaurant page.")

    html = raw.html or ""
    text = "\n".join(
        part for part in (primary_text(_html_with_src(html)), cut_at_discovery(raw.page_text)) if part
    )
    ld_nodes = json_ld_nodes(html, raw.json_ld)
    info = restaurant_json_ld(ld_nodes) or {}
    meta = meta_content(html)
    name = _first(info.get("name"), first_h1(html), (meta.get("og:title") or "").split("|")[0].strip())
    if name and "zomato" in name.lower():
        name = first_h1(html) or name

    address = _address(info)
    cuisines = split_cuisines(info.get("servesCuisine"))
    dining_rating, dining_count, delivery_rating, delivery_count = _ratings(text, info)
    phone = _phones(str(info.get("telephone") or ""), text)
    price = _first(info.get("priceRange"), _search(COST_RE, text))
    hours = _first(info.get("openingHours"), _hours(text))
    status = _opening_status(text)
    restaurant_id = _restaurant_id(html, info)
    images = _venue_images(raw, html, info, meta)
    gallery = [item for item in images if item.get("category") != "menu"]
    menu_images = [item["url"] for item in images if item.get("category") == "menu"]
    hero = gallery[0]["url"] if gallery else (images[0]["url"] if images else None)
    offers = _offers(text)
    amenities = _amenities(text)
    menu_pages = _menu_pages(text)
    if menu_images and menu_pages:
        menu_pages[0]["images"] = menu_images
    elif menu_images:
        menu_pages = [{"title": "Menu", "images": menu_images, "page_count": len(menu_images)}]
    text_menu = _menu_from_text(text, cuisines)
    harvested = categories_from_dom_menu(raw.dom_menu)
    categories = harvested or _menu_categories(raw.api_payloads) or text_menu
    if harvested and text_menu:
        merge_category_items(categories, text_menu)
        merge_item_images(categories, text_menu)
    fill_item_images_from_html(categories, html)
    maps_url = google_maps_url(html, text)
    geo = info.get("geo") if isinstance(info.get("geo"), dict) else {}
    if not maps_url and geo.get("latitude") and geo.get("longitude"):
        maps_url = f"https://www.google.com/maps?q={geo['latitude']},{geo['longitude']}"
    directions = maps_url
    if isinstance(info.get("hasmap"), str) and str(info["hasmap"]).startswith("http") and not maps_url:
        maps_url = info["hasmap"]
        directions = maps_url

    restaurant = Restaurant(
        name=name,
        rating=dining_rating or _ld_rating(info),
        rating_count=dining_count or _ld_rating_count(info),
        price_for_two=price,
        cuisines=cuisines,
        outlet=_ld_locality(info),
        address=address,
        image_url=hero,
        offers=offers,
        dining_rating=dining_rating,
        dining_rating_count=dining_count,
        delivery_rating=delivery_rating,
        delivery_rating_count=delivery_count,
        phone=phone,
        opening_hours=hours,
        opening_status=status,
        restaurant_id=str(restaurant_id) if restaurant_id else None,
        additional_information={"platform": "zomato"},
        zomato_rating=dining_rating or _ld_rating(info),
        zomato_url=platform_url_fields(raw.source_url)["zomato_url"],
    )
    venue = DineoutVenue(
        venue=name,
        restaurant_id=str(restaurant_id) if restaurant_id else None,
        hero_image=hero,
        rating=dining_rating or restaurant.rating,
        rating_count=dining_count or restaurant.rating_count,
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
        location={"address": address, "locality": restaurant.outlet, "maps_url": maps_url},
        location_map_image=None,
        directions_url=directions,
        source_url=raw.source_url,
        actions={"call": phone or "", "directions": directions or ""},
    )
    has_data = bool(name or categories or images or offers)
    status_code = "ok" if has_data else "failed"
    items = [item for category in categories for item in category.items]
    dish_images = sum(1 for item in items if item.image_url)
    image_count = dish_images if items else len(images)
    return Catalogue(
        source="zomato",
        source_url=raw.source_url,
        extraction_status=status_code,
        source_type="json_ld" if info else "dom",
        restaurant=restaurant,
        dineout=venue if has_data else None,
        categories=categories,
        item_count=len(items),
        image_count=image_count,
        error=None if has_data else (raw.reason or "Page was reachable but no Zomato venue data was found."),
        extraction=ExtractionMeta(
            ok=has_data,
            blocked=False,
            extraction_status=status_code,
            source_type="json_ld" if info else "dom",
            http_status=raw.http_status,
            data_locations=list(raw.data_locations or []),
        ),
    )


def _empty(raw: RawSource, status: str, error: str) -> Catalogue:
    return Catalogue(
        source="zomato",
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


def _address(info: dict[str, Any]) -> str | None:
    addr = info.get("address")
    if isinstance(addr, str) and addr.strip():
        return addr.strip()
    if isinstance(addr, dict):
        return _first(addr.get("streetAddress"), addr.get("addressLocality"))
    return None


def _ld_locality(info: dict[str, Any]) -> str | None:
    addr = info.get("address")
    if isinstance(addr, dict):
        value = _first(addr.get("addressLocality"))
        return None if is_distance_text(value) else value
    return None


def _ld_rating(info: dict[str, Any]) -> float | None:
    rating = info.get("aggregateRating")
    if isinstance(rating, dict):
        try:
            return float(rating.get("ratingValue"))
        except (TypeError, ValueError):
            return None
    return None


def _ld_rating_count(info: dict[str, Any]) -> str | None:
    rating = info.get("aggregateRating")
    if isinstance(rating, dict) and rating.get("ratingCount") is not None:
        return str(rating.get("ratingCount"))
    return None


def _ratings(text: str, info: dict[str, Any]) -> tuple[float | None, str | None, float | None, str | None]:
    collapsed = re.sub(r"\s+", " ", text.replace("\xa0", " "))
    match = DINING_RE.search(collapsed)
    if match:
        dining = _num(match.group(1))
        delivery = _num(match.group(3)) if match.group(3) != "-" else None
        dining_count = match.group(2).replace(",", "")
        delivery_count = None if match.group(4) == "-" else match.group(4).replace(",", "")
        return dining, dining_count, delivery, delivery_count
    return _ld_rating(info), _ld_rating_count(info), None, None


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "-") else None
    except (TypeError, ValueError):
        return None


def _phones(ld_phone: str, text: str) -> str | None:
    if ld_phone.strip():
        return ld_phone.strip()
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else None


def _search(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _hours(text: str) -> str | None:
    match = re.search(r"\d{1,2}(?:noon|am|pm|[.:]\d{2}\s*(?:am|pm)).{0,24}\d{1,2}(?:am|pm)", text, re.I)
    return match.group(0).strip() if match else None


def _opening_status(text: str) -> str | None:
    if re.search(r"\bopen now\b", text, re.I):
        return "Open now"
    if re.search(r"\bclosed\b", text, re.I):
        return "Closed"
    return None


def _restaurant_id(html: str, info: dict[str, Any]) -> str | None:
    match = RES_ID_RE.search(html)
    if match:
        return match.group(1)
    url = str(info.get("url") or "")
    digits = re.search(r"(\d{5,})", url)
    return digits.group(1) if digits else None


def _venue_images(raw: RawSource, html: str, info: dict[str, Any], meta: dict[str, str]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(url: str | None, category: str = "ambience") -> None:
        if not url or not str(url).startswith("http") or looks_like_ui_asset(url):
            return
        key = url.split("?")[0].lower()
        if key in seen:
            return
        if not ZOMATO_ASSET.search(url) and "zmtcdn.com/data" not in url.lower():
            return
        seen.add(key)
        images.append({"url": url, "category": category})

    image = info.get("image")
    if isinstance(image, str):
        add(image, "ambience")
    og = meta.get("og:image")
    if og and og.startswith("http"):
        add(og, "ambience")
    for item in html_images(venue_html(html), raw.source_url):
        alt = (item.get("alt") or "").lower()
        if re.search(r"similar|nearby|recommended|more restaurant", alt):
            continue
        url = item.get("url") or ""
        if "dish_photos" in url.lower():
            continue
        if re.search(r"similar|nearby|recommended|more restaurant", alt):
            continue
        if re.search(r"/data/menus|/menu", url, re.I) or "menu" in alt:
            category = "menu"
        elif "food" in alt or "/data/dish" in url.lower():
            category = "food"
        else:
            category = "ambience"
        add(url, category)
    scoped = venue_html(html)
    for url in re.findall(r"https://b\.zmtcdn\.com/data/pictures/[^\s\"'<>]+", scoped, flags=re.I):
        add(url, "ambience")
    for item in raw.dom_images or []:
        if isinstance(item, dict):
            add(item.get("url"))
    return images


def _offers(text: str) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    block = re.search(r"Dining Offers(.*?)(?:\bMenu\b|\bCuisines\b|\bSimilar restaurants\b|$)", text, re.I | re.S)
    blob = block.group(1) if block else text
    labeled = re.finditer(
        r"(PRE-BOOK OFFER|INSTANT OFFER|EXCLUSIVE OFFER|BANK OFFER|SURPRISE)\s+([^\n]+)",
        blob,
        re.I,
    )
    for match in labeled:
        kind = re.sub(r"\s+", " ", match.group(1)).strip()
        rest = re.sub(r"\s+", " ", match.group(2)).strip()
        title_match = re.search(
            r"(FLAT ₹[\d,]+ OFF|Flat\s+\d+%\s+OFF|₹[\d,]+\s+OFF|\d+%\s+off[^\n]{0,40}|Get a\s+scratch card)",
            rest,
            re.I,
        )
        title = (title_match.group(1) if title_match else rest).strip()
        detail = rest.replace(title, "", 1).strip() or None
        if any(title.lower() == existing["title"].lower() for existing in offers):
            continue
        offers.append({"title": title, "type": kind.title(), "description": detail})
    if offers:
        return offers[:8]
    for match in re.finditer(
        r"(FLAT ₹[\d,]+ OFF|[\d]+%\s*OFF[^\n]{0,80}|Get a\s+scratch card)",
        text,
        re.I,
    ):
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        if any(title.lower() == existing["title"].lower() for existing in offers):
            continue
        offers.append({"title": title, "type": "Dining offer"})
    return offers[:8]


def _amenities(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for hint in AMENITY_HINTS:
        if hint in lowered:
            found.append(hint.title() if hint.islower() else hint)
    return list(dict.fromkeys(found))


def _attach_dish_images(categories: list[MenuCategory], html: str, text: str) -> None:
    labeled: dict[str, str] = {}
    for tag in re.findall(r"<img\b[^>]*>", html or "", flags=re.I):
        attrs = {key.lower(): value for key, value in re.findall(r"""(\w+)\s*=\s*["']([^"']+)["']""", tag)}
        url = attrs.get("src") or attrs.get("data-src") or ""
        if "dish_photos" not in url.lower():
            srcset = attrs.get("srcset") or attrs.get("data-srcset") or ""
            parts = [part.strip().split(" ")[0] for part in srcset.split(",") if "dish_photos" in part]
            url = parts[-1] if parts else url
        alt = (attrs.get("alt") or "").strip()
        if alt and "dish_photos" in url.lower():
            labeled[alt.lower()] = url
    for category in categories:
        for item in category.items:
            if item.image_url:
                continue
            key = item.name.lower()
            if key in labeled:
                item.image_url = labeled[key]
                continue
            for alt, url in labeled.items():
                if alt.startswith(key) or key.startswith(alt):
                    item.image_url = url
                    break


def _menu_pages(text: str) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in MENU_SECTION_RE.finditer(text):
        title = match.group(1)
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        count = int(match.group(2))
        pages.append({"title": title, "page_count": count, "images": [], "identity": key})
    return pages


def _menu_categories(payloads: list[Any]) -> list[MenuCategory]:
    items_by_cat: dict[str, list[MenuItem]] = {}

    def walk(value: Any, category: str = "Menu") -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, category)
            return
        if not isinstance(value, dict):
            return
        name = value.get("name") or value.get("item_name") or value.get("dish_name")
        price = value.get("price") or value.get("min_price") or value.get("display_price")
        if isinstance(name, str) and name.strip() and _is_price(price):
            cat = str(value.get("category") or value.get("menu_category") or category).strip() or "Menu"
            items_by_cat.setdefault(cat, [])
            if not any(existing.name == name.strip() for existing in items_by_cat[cat]):
                items_by_cat[cat].append(
                    MenuItem(
                        name=name.strip(),
                        description=value.get("description") if isinstance(value.get("description"), str) else None,
                        price=_price(price),
                        food_type=value.get("dietary_slugs") or value.get("item_type"),
                        image_url=_image_from_node(value),
                    )
                )
            return
        next_cat = category
        for key in ("category_name", "menu_category", "name"):
            if isinstance(value.get(key), str) and "item" not in key:
                next_cat = value[key]
                break
        for child in value.values():
            walk(child, next_cat)

    for payload in payloads:
        walk(payload)
    return [MenuCategory(name=name, items=items) for name, items in items_by_cat.items() if items]


def photos_gallery_url(url: str) -> str | None:
    """View Gallery / Photos tab: {venue}/photos."""
    return _tab_url(url, "photos")


def order_menu_url(url: str) -> str | None:
    """Order Online tab: {venue}/order — left category list plus dish cards."""
    return _tab_url(url, "order")


def _tab_url(url: str, tab: str) -> str | None:
    match = ZOMATO_TAB_RE.search(url or "")
    if not match:
        return None
    base = match.group(1).split("?")[0].rstrip("/")
    for suffix in ("/order", "/menu", "/book", "/photos"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
    candidate = f"{base}/{tab}"
    current = (url or "").split("?")[0].rstrip("/").lower()
    if candidate.lower() == current:
        return None
    return candidate


def merge_zomato_images(base: Catalogue, extra: Catalogue) -> Catalogue:
    if extra.extraction_status != "ok" or not extra.dineout:
        return base
    existing = list(base.dineout.gallery_images if base.dineout else [])
    extra_images = list(extra.dineout.gallery_images or [])
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*existing, *extra_images]:
        url = (item.get("url") or "").split("?")[0].lower()
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(item)
    gallery = [item for item in merged if item.get("category") != "menu"]
    hero = gallery[0]["url"] if gallery else (merged[0]["url"] if merged else None)
    if base.restaurant:
        base.restaurant.image_url = base.restaurant.image_url or hero
    if base.dineout:
        base.dineout.hero_image = base.dineout.hero_image or hero
        base.dineout.gallery_images = gallery
        base.dineout.photos = [item["url"] for item in gallery]
        extra_videos = extra.dineout.videos if extra.dineout else []
        base.dineout.videos = dedupe_videos([*(base.dineout.videos or []), *(extra_videos or [])])
    item_images = sum(1 for category in base.categories for item in category.items if item.image_url)
    base.image_count = item_images
    return base


def merge_zomato_menu(base: Catalogue, extra: Catalogue) -> Catalogue:
    if extra.extraction_status != "ok" or not extra.categories:
        return base
    if _menu_score(extra) < _menu_score(base):
        return base
    base.categories = extra.categories
    base.item_count = extra.item_count
    item_images = sum(1 for category in base.categories for item in category.items if item.image_url)
    base.image_count = item_images
    return base


def _menu_score(catalogue: Catalogue) -> tuple[int, int, int]:
    images = sum(1 for category in catalogue.categories for item in category.items if item.image_url)
    items = sum(len(category.items) for category in catalogue.categories)
    return (images, items, len(catalogue.categories))


def _clean_markup(value: str) -> str:
    value = re.sub(r"</?customFont[^>]*>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip(" ,")


def _sidebar_categories(text: str, cuisine_skip: set[str]) -> list[MenuCategory]:
    categories: list[MenuCategory] = []
    seen: set[str] = set()
    for match in re.finditer(r"([A-Za-z][^,\n]{0,70}?)\s+\((\d{1,3})\)", text):
        name = _clean_markup(match.group(1))
        count = int(match.group(2))
        key = name.lower()
        if not name or key in seen or key in MENU_NOISE or key in cuisine_skip:
            continue
        if key in {"search within menu", "download the app"}:
            continue
        if 1 <= count <= 200 and 2 < len(name) < 60:
            seen.add(key)
            categories.append(MenuCategory(name=name, items=[], item_count=count))
    return categories


def _menu_start_index(block: str) -> int:
    for pattern in (r"Search within menu", r"Download the App"):
        match = re.search(pattern, block, re.I)
        if match:
            return match.end()
    return 0


def _menu_start(block: str) -> str:
    for pattern in (r"Search within menu", r"Download the App"):
        match = re.search(pattern, block, re.I)
        if match:
            return block[match.end() :]
    return block


def _menu_tokens(block: str) -> list[str]:
    prepared = DISH_PHOTO_RE.sub(lambda match: f"\n{match.group(0)}\n", block)
    prepared = re.sub(r",(?=https://b\.zmtcdn\.com/data/dish_photos)", "\n", prepared)
    tokens: list[str] = []
    for line in prepared.splitlines():
        piece = _clean_markup(line)
        if piece:
            tokens.append(piece)
    return tokens


def _menu_from_text(text: str, cuisines: list[str] | None = None) -> list[MenuCategory]:
    cut = RELATED_CUT_RE.search(text)
    full = text[: cut.start()] if cut else text
    cuisine_skip = {item.lower() for item in (cuisines or [])} | CUISINE_ONLY
    start_at = _menu_start_index(full)
    seeded = _sidebar_categories(full[:start_at] if start_at else "", cuisine_skip)
    sidebar = {category.name.lower() for category in seeded}
    tokens = _menu_tokens(_menu_start(full))
    categories: list[MenuCategory] = list(seeded)
    current: MenuCategory | None = categories[0] if categories else None
    pending_desc: MenuItem | None = None
    pending_image: str | None = None

    def switch(heading: str, count: int | None) -> None:
        nonlocal current, pending_desc
        key = heading.lower()
        for category in categories:
            if category.name.lower() == key:
                current = category
                if count is not None:
                    current.item_count = count
                pending_desc = None
                return
        current = MenuCategory(name=heading, items=[], item_count=count)
        categories.append(current)
        pending_desc = None

    for index, line in enumerate(tokens):
        nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
        if DISH_PHOTO_RE.fullmatch(line):
            if pending_desc and not pending_desc.image_url:
                pending_desc.image_url = line
                pending_desc.source_image_url = pending_desc.source_image_url or line
            else:
                pending_image = line
            continue
        counted = CATEGORY_COUNTS_RE.match(line)
        heading = _as_heading(line, sidebar, cuisine_skip, nxt)
        if heading:
            switch(heading, int(counted.group(2)) if counted else None)
            continue
        if current is None:
            continue
        if _is_menu_noise(line, cuisine_skip):
            continue
        if line.lower().startswith("lic. no"):
            break
        if _looks_like_description(line) and pending_desc and not pending_desc.description:
            pending_desc.description = line
            continue
        if pending_desc and pending_desc.price is None and _looks_like_item_price(line):
            pending_desc.price = _price(line)
            continue
        if not _looks_like_dish_name(line):
            continue
        item = MenuItem(name=line, image_url=pending_image, source_image_url=pending_image)
        if nxt and _looks_like_item_price(nxt):
            item.price = _price(nxt)
        current.items.append(item)
        pending_desc = item
        pending_image = None
    merged: dict[str, MenuCategory] = {}
    order: list[str] = []
    for category in categories:
        existing = merged.get(category.name)
        if existing is None:
            merged[category.name] = category
            order.append(category.name)
            continue
        seen = {item.name.lower() for item in existing.items}
        for item in category.items:
            if item.name.lower() not in seen:
                existing.items.append(item)
                seen.add(item.name.lower())
        if existing.item_count is None:
            existing.item_count = category.item_count
    filled = [merged[name] for name in order]
    if any(category.items for category in filled):
        return filled
    return []


def _as_heading(line: str, sidebar: set[str], cuisine_skip: set[str], nxt: str) -> str | None:
    counted = CATEGORY_COUNTS_RE.match(line)
    candidate = counted.group(1) if counted else line
    key = candidate.lower().strip("’'")
    if counted and 1 <= int(counted.group(2)) <= 200 and len(candidate) < 60:
        return candidate
    if key in sidebar:
        return candidate
    if key in MENU_HEADINGS:
        return candidate
    if key in cuisine_skip or key in MENU_NOISE:
        return None
    if DISH_PHOTO_RE.search(nxt) and 3 <= len(candidate) < 50 and not _looks_like_description(candidate):
        if key in sidebar or key in MENU_HEADINGS:
            return candidate
        return None
    return None


def _is_menu_noise(line: str, cuisine_skip: set[str]) -> bool:
    lowered = line.lower().strip()
    if lowered in MENU_NOISE or lowered in cuisine_skip:
        return True
    if len(line) < 3:
        return True
    if re.fullmatch(r"\+?\d[\d\s-]{8,}\d", line):
        return True
    if re.fullmatch(r"[\d.]+", line) or re.fullmatch(r"\d[\d,.]*[kK]?", line):
        return True
    if re.search(r"\b(open now|dining ratings|delivery ratings)\b", lowered):
        return True
    if "bangalore" in lowered and re.search(r"\d", line):
        return True
    if re.search(r"\d{1,2}\s*(am|pm|noon)", lowered) and re.search(r"(today|am|pm)", lowered):
        return True
    if line.lower().startswith("http") and "dish_photos" not in line.lower():
        return True
    if "customfont" in lowered or "web/assets" in lowered:
        return True
    if re.fullmatch(r"\d+\s+items?", lowered) or re.fullmatch(r"\d+\s+min", lowered):
        return True
    return False


def _looks_like_item_price(line: str) -> bool:
    cleaned = line.strip().replace(",", "")
    return bool(re.fullmatch(r"(?:₹|rs\.?|inr)?\s*\d+(?:\.\d+)?", cleaned, flags=re.I))


def _looks_like_dish_name(line: str) -> bool:
    if not re.search(r"[A-Za-z]", line):
        return False
    if _looks_like_item_price(line):
        return False
    if len(line) > 80:
        return False
    if line.lower() in CUISINE_ONLY:
        return False
    return True


def _looks_like_description(line: str) -> bool:
    if len(line) > 48:
        return True
    return bool(re.search(r"\b(served|cooked|inspired|favourite|pieces|homemade|read more)\b", line, re.I))


def _is_price(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str) and re.search(r"\d", value):
        return True
    if isinstance(value, dict) and (value.get("amount") or value.get("display_text")):
        return True
    return False


def _price(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        return _price(value.get("amount") or value.get("display_text"))
    if isinstance(value, str):
        match = re.search(r"[\d.]+", value.replace(",", ""))
        return float(match.group(0)) if match else None
    return None


def _image_from_node(node: dict[str, Any]) -> str | None:
    for key in ("image_url", "image", "thumb", "url"):
        value = node.get(key)
        if isinstance(value, str) and value.startswith("http") and not looks_like_ui_asset(value):
            return value
    return None
