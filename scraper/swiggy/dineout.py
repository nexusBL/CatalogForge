from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from scraper.swiggy.models import Catalogue, DineoutVenue, Restaurant
from scraper.swiggy.parser import _first_str, _image_url, _type_name, _walk

RECOMMENDATION_HINTS = (
    "recommended options",
    "recommended",
    "near ",
    "nearby",
    "brands near",
    "more restaurants",
    "more american",
    "similar restaurant",
    "other restaurant",
    "you may also",
    "people also",
    "similar places",
    "also like",
    "explore more",
    "restaurants near you",
)

NOT_OFFER_TITLES = {
    "photos",
    "gallery",
    "menu",
    "location",
    "amenities",
    "about",
    "cuisines",
    "popular dishes",
    "about dineout",
    "offers",
    "offers for you",
    "pre-booking offers",
    "add-on offers",
    "offer terms & conditions",
    "terms & conditions",
}

OFFER_TITLE_HINTS = (
    "% off",
    "%off",
    "cashback",
    "discount",
    "free ",
    "pre-book",
    "prebook",
    "offer",
    "deal",
    "coupon",
    "promo",
)

MENU_IMAGE_ALTS = {"breakfast", "food", "bar", "menu", "drinks", "beverages"}

UI_IMAGE_HINTS = (
    "logo",
    "icon",
    "placeholder",
    "sprite",
    "swiggy-logo",
    "badge",
    "popular_dishes",
    "highlight_star",
    "rx_highlight",
    "dineout/details",
    "plus_icon",
    "cross.png",
    "seo%20web",
    "seo web",
    "iconleft",
    "iconright",
    "iconleft.png",
    "iconright.png",
)
OFFER_IMAGE_HINTS = (
    "oneexclusive",
    "marketing_banners",
    "/images/offers/",
    "loyalty/nba",
    "rx-card/offer",
)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
SLIDE_ALT_RE = re.compile(r"^slide\s+\d+$", re.I)


@dataclass
class PrimaryVenue:
    restaurant_id: str | None
    slug: str | None
    name: str | None


def is_dineout_url(url: str | None) -> bool:
    return "dineout" in (url or "").lower()


def primary_venue_from_url(url: str) -> PrimaryVenue:
    path = urlparse(url or "").path.rstrip("/")
    parts = [part for part in path.split("/") if part and part.lower() != "dineout"]
    slug = parts[-1] if parts else None
    restaurant_id = None
    name = None
    if slug:
        match = re.search(r"-(\d+)$", slug)
        if match:
            restaurant_id = match.group(1)
            slug_name = slug[: match.start()]
        else:
            slug_name = slug
        name = _name_from_slug(slug_name)
    return PrimaryVenue(restaurant_id=restaurant_id, slug=slug, name=name)


def enrich_dineout(
    catalogue: Catalogue,
    payloads: list[Any],
    html: str | None = None,
    dom_images: list[dict[str, Any]] | None = None,
) -> Catalogue:
    dineout_page = is_dineout_url(catalogue.source_url)
    venue = build_dineout_venue(
        catalogue.restaurant,
        payloads,
        catalogue.source_url,
        html=html,
        dom_images=dom_images,
    )
    if not _dineout_has_content(venue):
        return catalogue
    catalogue.dineout = venue
    extra_images = _dineout_image_count(venue)
    if extra_images:
        catalogue.image_count = max(catalogue.image_count, extra_images)
    if dineout_page:
        if catalogue.extraction_status == "failed":
            catalogue.extraction_status = "ok"
            catalogue.error = None
            catalogue.extraction.ok = True
            catalogue.extraction.extraction_status = "ok"
            catalogue.extraction.error = None
        if venue.venue and (
            not catalogue.restaurant.name or not _names_match(catalogue.restaurant.name, venue.venue)
        ):
            catalogue.restaurant.name = venue.venue
            catalogue.restaurant.image_url = venue.hero_image
            catalogue.restaurant.rating = venue.rating
            catalogue.restaurant.rating_count = venue.rating_count
            catalogue.restaurant.cuisines = list(venue.cuisines or [])
            catalogue.restaurant.price_for_two = venue.price_for_two
            catalogue.restaurant.outlet = (venue.location or {}).get("outlet") or (venue.location or {}).get("locality")
            catalogue.restaurant.address = (venue.location or {}).get("address")
            catalogue.categories = []
            catalogue.item_count = 0
    return catalogue


def build_dineout_venue(
    restaurant: Restaurant,
    payloads: list[Any],
    source_url: str,
    html: str | None = None,
    dom_images: list[dict[str, Any]] | None = None,
) -> DineoutVenue:
    primary = primary_venue_from_url(source_url)
    extra = restaurant.additional_information if isinstance(restaurant.additional_information, dict) else {}
    primary_nodes = list(_iter_primary_nodes(payloads))
    recommendation_names = _recommendation_names(payloads)
    info = _select_primary_info(primary_nodes, primary, restaurant)
    name = _first_str(info.get("name"), info.get("restaurantName"), restaurant.name, primary.name)
    hero = _image_url(
        info.get("cloudinaryImageId") or info.get("imageId") or info.get("image")
    )
    if not hero and _names_match(restaurant.name, name or primary.name):
        hero = restaurant.image_url
    if name and any(_names_match(name, other) for other in recommendation_names):
        name = primary.name or restaurant.name
        hero = restaurant.image_url if _names_match(restaurant.name, primary.name) else hero
    offers = _normalize_offers(_primary_offers(info, restaurant.offers, primary_nodes), recommendation_names)
    menu_pages = _extract_menu_pages(primary_nodes)
    media = _primary_media_files(payloads, primary)
    excluded = _foreign_image_keys(payloads, primary)
    ambience_media = [item for item in media if (item.get("category") or "") == "ambience"]
    if not hero and ambience_media:
        hero = ambience_media[0]["url"]
    gallery = _dedupe_gallery(
        [*_extract_gallery(primary_nodes, None), *media, *_gallery_from_html(html, excluded)],
        hero,
    )
    if not hero:
        for item in gallery:
            if (item.get("category") or "") == "ambience":
                hero = item["url"]
                break
        if not hero and gallery:
            hero = gallery[0]["url"]
    photos = [item["url"] for item in gallery]
    amenities = _extract_amenities(extra, primary_nodes, info)
    popular = [
        dish
        for dish in _extract_popular_dishes(extra, primary_nodes, info)
        if not any(_names_match(dish, other) for other in recommendation_names)
        and not _is_discovery_title(dish)
    ]
    for dish in _popular_from_html(html):
        if any(_names_match(dish, other) for other in recommendation_names) or _is_discovery_title(dish):
            continue
        if dish not in popular:
            popular.append(dish)
    opening = _opening_hours(info, extra)
    availability = info.get("availability") if isinstance(info.get("availability"), dict) else {}
    opening_status = _first_str(availability.get("opened"), availability.get("message"))
    if extra.get("isOpen") is True and not opening_status:
        opening_status = "Open"
    phone = _phone(info, extra, primary_nodes)
    map_url = _map_url(info, extra, primary_nodes)
    map_image = _map_image(primary_nodes)
    loc_info = info.get("locationInfo") if isinstance(info.get("locationInfo"), dict) else {}
    distance = _plausible_local_distance(_first_str(loc_info.get("distanceString")))
    location = _location(restaurant, extra, info)
    formatted = _first_str(loc_info.get("formattedAddress"))
    page_address = _address_from_html(html)
    if page_address and (not formatted or len(page_address) > len(formatted)):
        location["address"] = page_address
        if not location.get("location"):
            location["location"] = page_address
    elif formatted:
        location["address"] = formatted
        if not location.get("location"):
            location["location"] = formatted
    if distance:
        location["distance"] = distance
    coords = _coords_from_url(map_url) or _coords_from_location_info(loc_info)
    if coords and not map_url:
        map_url = f"https://www.google.com/maps/dir/?api=1&destination={coords[0]},{coords[1]}"
    map_url = _strip_maps_origin(map_url)
    maps_link = f"https://www.google.com/maps?q={coords[0]},{coords[1]}" if coords else map_url
    if not map_image and coords:
        map_image = _static_map_url(coords[0], coords[1])
    if map_image:
        location["map_image"] = map_image
    if maps_link:
        location["maps_url"] = maps_link
    if map_url:
        location["directions_url"] = map_url
    actions: dict[str, str] = {}
    if map_url:
        actions["directions"] = map_url
    if phone:
        actions["call"] = phone
    rating = _to_number(info.get("avgRating") or info.get("avgRatingString") or restaurant.rating)
    rating_count = info.get("totalRatings") or info.get("totalRatingsString") or restaurant.rating_count
    cuisines = info.get("cuisines") if isinstance(info.get("cuisines"), list) else list(restaurant.cuisines or [])
    cuisines = [item for item in cuisines if isinstance(item, str) and item.strip()]
    price = info.get("costForTwoMessage") or info.get("costForTwo") or restaurant.price_for_two
    restaurant_id = str(info.get("id") or info.get("resId") or primary.restaurant_id or "") or None
    venue = DineoutVenue(
        venue=name,
        restaurant_id=restaurant_id,
        hero_image=hero,
        rating=rating if isinstance(rating, (int, float)) else restaurant.rating,
        rating_count=rating_count,
        cuisines=cuisines,
        price_for_two=price,
        opening_hours=opening,
        opening_status=opening_status,
        actions=actions,
        offers=offers,
        menu_pages=menu_pages,
        popular_dishes=popular,
        photos=photos,
        gallery_images=gallery,
        videos=_extract_videos(html),
        amenities=amenities,
        location=location,
        location_map_image=map_image,
        directions_url=map_url,
        phone=phone,
        source_url=source_url or None,
    )
    if is_dineout_url(source_url):
        _apply_classified_images(venue, html, dom_images)
        venue.gallery_images = [
            item
            for item in _dedupe_gallery(venue.gallery_images, venue.hero_image)
            if _image_filename(item.get("url") or "") not in excluded
            and not _is_offer_asset(item.get("url") or "")
        ]
        venue.photos = [item["url"] for item in venue.gallery_images]
        venue.videos = _dedupe_videos([*(venue.videos or []), *_extract_videos(html)])
        _assign_offer_images(venue, html, dom_images)
        if coords and not venue.location_map_image:
            venue.location_map_image = _static_map_url(coords[0], coords[1])
            if isinstance(venue.location, dict):
                venue.location["map_image"] = venue.location_map_image
        if maps_link and isinstance(venue.location, dict) and not venue.location.get("maps_url"):
            venue.location["maps_url"] = maps_link
    return venue


def _dineout_has_content(venue: DineoutVenue) -> bool:
    return bool(
        venue.venue
        or venue.hero_image
        or venue.offers
        or venue.menu_pages
        or venue.photos
        or venue.gallery_images
        or venue.amenities
        or venue.popular_dishes
        or venue.location
    )


def _dineout_image_count(venue: DineoutVenue) -> int:
    urls: list[str] = []
    if venue.hero_image:
        urls.append(venue.hero_image)
    for item in venue.gallery_images or []:
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            urls.append(item["url"])
    urls.extend(url for url in (venue.photos or []) if isinstance(url, str))
    for page in venue.menu_pages:
        if page.get("image"):
            urls.append(page["image"])
        urls.extend(image for image in (page.get("images") or []) if isinstance(image, str))
    if venue.location_map_image:
        urls.append(venue.location_map_image)
    seen: set[str] = set()
    count = 0
    for url in urls:
        if not url or _looks_like_ui_image(url):
            continue
        key = _image_filename(url)
        if key in seen:
            continue
        seen.add(key)
        count += 1
    return count


def _name_from_slug(slug: str) -> str | None:
    if not slug:
        return None
    parts = [part for part in slug.split("-") if part]
    words: list[str] = []
    index = 0
    while index < len(parts):
        if index + 1 < len(parts) and parts[index + 1] == "s":
            words.append(parts[index].capitalize() + "'s")
            index += 2
            continue
        words.append(parts[index].capitalize())
        index += 1
    return " ".join(words) or None


def _names_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return re.sub(r"[^a-z0-9]+", "", left.lower()) == re.sub(r"[^a-z0-9]+", "", right.lower())


def _is_recommendation_context(node: dict[str, Any]) -> bool:
    texts: list[str] = []
    for key in ("title", "header", "text", "subtitle", "heading", "accessibility"):
        value = node.get(key)
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            texts.extend(str(item) for item in value.values() if isinstance(item, str))
    blob = " ".join(texts).lower()
    return any(hint in blob for hint in RECOMMENDATION_HINTS)


def _is_recommendation_widget(node: dict[str, Any]) -> bool:
    type_name = _type_name(node).lower()
    widget_id = str(node.get("id") or node.get("widgetId") or "").lower()
    if "similardinersone" in type_name or "similarrestaurant" in type_name:
        return True
    if any(token in widget_id for token in ("similar", "recommend")):
        return True
    if _is_recommendation_context(node) and isinstance(node.get("restaurants"), list):
        return True
    grid = node.get("gridElements")
    if isinstance(grid, dict) and _is_recommendation_context(node):
        return True
    if isinstance(grid, dict):
        inner = grid.get("infoWithStyle") if isinstance(grid.get("infoWithStyle"), dict) else {}
        if "similar" in _type_name(inner).lower():
            return True
    return False


def _iter_primary_nodes(payloads: list[Any]):
    for payload in payloads:
        yield from _walk_skip_recommendations(payload)


def _walk_skip_recommendations(obj: Any):
    if isinstance(obj, dict):
        if _is_recommendation_widget(obj):
            return
        yield obj
        for value in obj.values():
            yield from _walk_skip_recommendations(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_skip_recommendations(item)


def _recommendation_names(payloads: list[Any]) -> set[str]:
    names: set[str] = set()
    for payload in payloads:
        for node in _walk(payload):
            if not isinstance(node, dict) or not _is_recommendation_context(node):
                continue
            for child in _walk(node):
                if not isinstance(child, dict):
                    continue
                info = child.get("info") if isinstance(child.get("info"), dict) else child
                name = _first_str(info.get("name"), info.get("restaurantName"))
                if name:
                    names.add(name)
    return names


def _select_primary_info(nodes: list[dict[str, Any]], primary: PrimaryVenue, restaurant: Restaurant) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for node in nodes:
        info = node.get("info") if isinstance(node.get("info"), dict) else node
        name = _first_str(info.get("name"), info.get("restaurantName"))
        rid = str(info.get("id") or info.get("resId") or node.get("id") or "")
        slug = ""
        slugs = info.get("slugs") if isinstance(info.get("slugs"), dict) else {}
        if slugs:
            slug = str(slugs.get("restaurant") or "")
        if not name and not rid:
            continue
        if primary.restaurant_id and rid == primary.restaurant_id:
            return info
        if primary.slug and primary.slug in slug:
            return info
        if primary.name and _names_match(name, primary.name):
            return info
        if restaurant.name and _names_match(name, restaurant.name):
            candidates.insert(0, info)
        elif name:
            candidates.append(info)
    if candidates:
        return candidates[0]
    extra = restaurant.additional_information if isinstance(restaurant.additional_information, dict) else {}
    return {
        "name": restaurant.name,
        "cloudinaryImageId": restaurant.image_url,
        "avgRating": restaurant.rating,
        "totalRatingsString": restaurant.rating_count,
        "cuisines": restaurant.cuisines,
        "costForTwoMessage": restaurant.price_for_two,
        "locality": extra.get("locality"),
        "areaName": extra.get("areaName"),
        "city": extra.get("city"),
        "id": extra.get("id"),
        "availability": extra.get("availability"),
        "sla": extra.get("sla"),
    }


def _is_discovery_title(title: str | None) -> bool:
    text = (title or "").strip().lower()
    if not text:
        return False
    if text in NOT_OFFER_TITLES:
        return True
    return any(hint in text for hint in RECOMMENDATION_HINTS)


def _looks_like_real_offer(node: Any) -> bool:
    offer = _one_offer(node)
    if not offer:
        return False
    if _is_discovery_title(offer["title"]):
        return False
    if isinstance(node, dict):
        type_name = _type_name(node).lower()
        if any(token in type_name for token in ("offer", "deal", "promo", "coupon", "discount")):
            return True
        if node.get("couponCode") or node.get("offerTag") or node.get("discountTag") or node.get("offerValue"):
            return True
        if node.get("name") and node.get("cuisines"):
            return False
    blob = " ".join(
        str(offer.get(key) or "") for key in ("title", "description", "discount", "code")
    ).lower()
    return any(hint in blob for hint in OFFER_TITLE_HINTS)


def _primary_offers(info: dict[str, Any], restaurant_offers: list[Any], nodes: list[dict[str, Any]]) -> list[Any]:
    offers: list[Any] = []
    for item in restaurant_offers or []:
        if _looks_like_real_offer(item):
            offers.append(item)
    for key in ("aggregatedDiscountInfoV3", "aggregatedDiscountInfoV2", "offerDetails"):
        value = info.get(key)
        if value not in (None, "", [], {}) and _looks_like_real_offer(value):
            offers.append(value)
    for node in nodes:
        if _is_recommendation_context(node):
            continue
        if node.get("name") and node.get("cuisines"):
            continue
        if _looks_like_real_offer(node):
            offers.append(node)
    return offers


def _normalize_offers(raw_offers: list[Any], recommendation_names: set[str]) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in raw_offers or []:
        offer = _one_offer(node)
        if not offer:
            continue
        if _is_discovery_title(offer["title"]):
            continue
        if any(_names_match(offer["title"], name) for name in recommendation_names):
            continue
        marker = offer["title"]
        if marker in seen:
            continue
        seen.add(marker)
        offers.append(offer)
    return offers


def _one_offer(node: Any) -> dict[str, Any] | None:
    if isinstance(node, str) and node.strip():
        if _is_discovery_title(node):
            return None
        return {"title": node.strip()}
    if not isinstance(node, dict):
        return None
    title = _first_str(
        node.get("header"),
        node.get("title"),
        node.get("discountTag"),
        node.get("offerTag"),
        node.get("primary"),
    )
    description = _first_str(
        node.get("description"),
        node.get("subHeader"),
        node.get("couponCode"),
        node.get("offerDescription"),
        node.get("terms"),
    )
    if not title and isinstance(node.get("header"), dict):
        title = _first_str(node["header"].get("title"), node["header"].get("text"))
    if not title or _is_discovery_title(title):
        return None
    offer: dict[str, Any] = {"title": title}
    if description:
        offer["description"] = description
    code = _first_str(node.get("couponCode"), node.get("code"))
    if code:
        offer["code"] = code
    validity = _first_str(node.get("validTill"), node.get("validity"), node.get("expiry"))
    if validity:
        offer["validity"] = validity
    discount = _first_str(node.get("discount"), node.get("offerValue"))
    if discount:
        offer["discount"] = discount
    image = _offer_image_from_node(node)
    if image:
        offer["image"] = image
    return offer


def _offer_image_from_node(node: dict[str, Any]) -> str | None:
    logo = node.get("offerLogo")
    candidates = [
        node.get("logo"),
        node.get("image"),
        node.get("offerImage"),
        node.get("creativeId"),
        logo.get("logo") if isinstance(logo, dict) else logo,
        logo.get("url") if isinstance(logo, dict) else None,
    ]
    for candidate in candidates:
        url = candidate if isinstance(candidate, str) and candidate.startswith("http") else _image_url(candidate)
        if url and not _looks_like_ui_image(url) and "rx-card/offer" not in url.lower():
            return url
    return None


def _extract_menu_pages(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in nodes:
        type_name = _type_name(node).lower()
        looks_menu = "dineoutmenu" in type_name or "menucard" in type_name or "menupage" in type_name
        title = _first_str(node.get("title"), node.get("name"), node.get("menuType"), node.get("category"))
        title_is_menu = bool(title) and (
            title.lower() in {"breakfast", "food", "bar", "menu"} or "menu" in title.lower()
        )
        images = _collect_images(node)
        page_count = node.get("pageCount") or node.get("pages") or node.get("imageCount") or (len(images) or None)
        if looks_menu and (images or title):
            pass
        elif title and images and node.get("price") in (None, "", 0) and title_is_menu:
            pass
        else:
            continue
        identity = str(node.get("id") or title or (images[0] if images else ""))
        if identity in seen:
            continue
        seen.add(identity)
        page: dict[str, Any] = {"title": title or "Menu", "identity": identity}
        if images:
            page["images"] = images
            page["image"] = images[0]
        if isinstance(page_count, int) and page_count > 0:
            page["page_count"] = page_count
        source = _first_str(node.get("url"), node.get("ctaLink"))
        if source:
            page["source_url"] = source
        pages.append(page)
    return _collapse_menu_pages(pages)


def _looks_like_menu_asset(url: str) -> bool:
    filename = _image_filename(url)
    return any(token in filename for token in ("foodmenu", "beveragemenu", "menudaffy", "menu-"))


def _primary_media_files(payloads: list[Any], primary: PrimaryVenue) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not primary.restaurant_id:
        return files
    for payload in payloads:
        for node in _walk(payload):
            if not isinstance(node, dict):
                continue
            info = node.get("info") if isinstance(node.get("info"), dict) else node
            rid = str(info.get("id") or info.get("resId") or "")
            if rid != str(primary.restaurant_id):
                continue
            media = info.get("mediaFiles") or node.get("mediaFiles")
            if not isinstance(media, list):
                continue
            for item in media:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("type") or "IMAGE").upper()
                if kind and kind not in {"IMAGE", "PHOTO"}:
                    continue
                url = _image_url(item.get("url") or item.get("cloudinaryImageId") or item.get("imageId"))
                if not url or _looks_like_ui_image(url) or _looks_like_menu_asset(url):
                    continue
                key = _image_filename(url)
                if key in seen:
                    continue
                seen.add(key)
                entry: dict[str, Any] = {"url": url}
                category = _first_str(item.get("name"), item.get("category"), item.get("alt"))
                if category:
                    entry["category"] = category.lower()
                files.append(entry)
    return files


ASSET_IMAGE_RE = re.compile(
    r"https://(?:dineout-media-assets|media-assets)\.swiggy\.com/[^\"'\\s>]+RESTAURANT_IMAGE_SERVICE[^\"'\\s>]+",
    re.I,
)


def _foreign_image_keys(payloads: list[Any], primary: PrimaryVenue) -> set[str]:
    keys: set[str] = set()
    if not primary.restaurant_id:
        return keys
    for payload in payloads:
        for node in _walk(payload):
            if not isinstance(node, dict):
                continue
            info = node.get("info") if isinstance(node.get("info"), dict) else node
            rid = str(info.get("id") or info.get("resId") or "")
            if not rid or rid == str(primary.restaurant_id):
                continue
            media = info.get("mediaFiles") or node.get("mediaFiles")
            if not isinstance(media, list):
                continue
            for item in media:
                url = None
                if isinstance(item, str):
                    url = _image_url(item)
                elif isinstance(item, dict):
                    url = _image_url(item.get("url") or item.get("cloudinaryImageId"))
                if url:
                    keys.add(_image_filename(url))
    return keys


def _gallery_from_html(html: str | None, excluded: set[str]) -> list[dict[str, Any]]:
    if not html:
        return []
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in ASSET_IMAGE_RE.findall(html):
        url = url.rstrip("\\.,)")
        if _looks_like_ui_image(url) or _looks_like_menu_asset(url) or _is_offer_asset(url):
            continue
        key = _image_filename(url)
        if key in seen or key in excluded:
            continue
        seen.add(key)
        photos.append({"url": url})
    return photos


def _dedupe_gallery(items: list[dict[str, Any]], hero: str | None = None) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    if hero:
        ordered.append({"url": hero, "category": "ambience"})
    ordered.extend(item for item in items if isinstance(item, dict) and item.get("url"))
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ordered:
        url = item.get("url")
        if not isinstance(url, str) or not url:
            continue
        if _looks_like_ui_image(url) or _looks_like_menu_asset(url) or _is_offer_asset(url):
            continue
        key = _image_filename(url)
        if key in seen:
            continue
        seen.add(key)
        photos.append(item)
    return photos


def _plausible_local_distance(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    match = re.search(r"([\d.]+)\s*(km|m)\b", text, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    kilometres = amount / 1000.0 if unit == "m" else amount
    if kilometres > 20:
        return None
    return text


def _strip_maps_origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() != "origin"]
    return urlunparse(parsed._replace(query=urlencode(query)))


def _address_from_html(html: str | None) -> str | None:
    if not html:
        return None
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\s+\n", "\n", text)
    match = re.search(
        r"Location\s+(?:\d+(?:\.\d+)?\s*(?:km|m)\s*[•·,]\s*)?([^\n]{20,220})",
        text,
        re.I,
    )
    if not match:
        return None
    address = re.sub(r"\s+", " ", match.group(1)).strip(" •·,")
    if len(address) < 12:
        return None
    if any(hint in address.lower() for hint in RECOMMENDATION_HINTS):
        return None
    return address


def _coords_from_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    match = re.search(r"(?:[?&](?:q|query|destination)=)(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", url)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", url)
    if match:
        return match.group(1), match.group(2)
    return None


def _coords_from_location_info(loc_info: dict[str, Any]) -> tuple[str, str] | None:
    geometry = loc_info.get("geometry") if isinstance(loc_info.get("geometry"), dict) else {}
    lat = loc_info.get("latitude") or loc_info.get("lat") or geometry.get("latitude") or geometry.get("lat")
    lng = loc_info.get("longitude") or loc_info.get("lng") or geometry.get("longitude") or geometry.get("lng")
    if lat not in (None, "") and lng not in (None, ""):
        return str(lat), str(lng)
    return None


def _static_map_url(lat: str, lng: str) -> str:
    return (
        f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lng}"
        f"&zoom=16&size=800x400&maptype=mapnik&markers={lat},{lng},lightblue1"
    )


def _image_filename(url: str) -> str:
    return url.split("/")[-1].split("?")[0].lower()


def _collapse_menu_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for page in pages:
        title = page.get("title") or "Menu"
        key = title.casefold()
        if key not in grouped:
            grouped[key] = {
                "title": title,
                "images": [],
                "identity": page.get("identity") or key,
            }
            order.append(key)
        seen_files = {_image_filename(url) for url in grouped[key]["images"]}
        for image in page.get("images") or ([page["image"]] if page.get("image") else []):
            filename = _image_filename(image)
            if filename in seen_files:
                continue
            seen_files.add(filename)
            grouped[key]["images"].append(image)
        page_count = page.get("page_count")
        if isinstance(page_count, int) and page_count > 0:
            grouped[key]["page_count"] = max(grouped[key].get("page_count") or 0, page_count)
    collapsed: list[dict[str, Any]] = []
    for key in order:
        item = grouped[key]
        if item["images"]:
            item["image"] = item["images"][0]
            item["page_count"] = max(item.get("page_count") or 0, len(item["images"]))
        collapsed.append(item)
    return collapsed


def _extract_gallery(nodes: list[dict[str, Any]], hero: str | None) -> list[dict[str, Any]]:
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()
    if hero:
        seen.add(hero)
    for node in nodes:
        type_name = _type_name(node).lower()
        title = _first_str(node.get("title"), node.get("name"), node.get("category")) or ""
        if "dineoutmenu" in type_name or "menucard" in type_name or "menupage" in type_name:
            continue
        is_gallery = "gallery" in type_name or "photo" in type_name or "imagegrid" in type_name or "carousel" in type_name
        if title.lower() in {"photos", "gallery", "show all images", "view all images", "ambience"}:
            is_gallery = True
        if SLIDE_ALT_RE.match(title.strip()):
            is_gallery = True
        if not is_gallery:
            continue
        category = None
        lowered = title.lower()
        if "ambience" in lowered or "interior" in lowered:
            category = "ambience"
        elif "food" in lowered:
            category = "food"
        for image in _collect_images(node):
            if image in seen or _looks_like_ui_image(image):
                continue
            seen.add(image)
            item: dict[str, Any] = {"url": image}
            if category:
                item["category"] = category
            photos.append(item)
    return photos


def _collect_images(node: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for key in ("cloudinaryImageId", "imageId", "image", "url", "src"):
        image = _image_url(node.get(key)) if key != "url" or not str(node.get(key) or "").startswith("http") else str(node.get(key))
        if key == "url" and isinstance(node.get("url"), str) and node["url"].startswith("http") and any(
            hint in node["url"].lower() for hint in ("image", "cloudinary", "swiggy")
        ):
            image = node["url"]
        if image and image not in images and not _looks_like_ui_image(image):
            images.append(image)
    nested = node.get("images") or node.get("photos") or node.get("imageIds") or node.get("mediaFiles")
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, str):
                image = _image_url(item) or (item if item.startswith("http") else None)
            elif isinstance(item, dict):
                if str(item.get("type") or "").upper() == "VIDEO":
                    continue
                image = _image_url(item.get("cloudinaryImageId") or item.get("imageId") or item.get("url"))
            else:
                image = None
            if image and image not in images and not _looks_like_ui_image(image):
                images.append(image)
    return images


def _looks_like_ui_image(url: str) -> bool:
    lowered = url.lower()
    return any(hint in lowered for hint in UI_IMAGE_HINTS)


def _html_attr(tag: str, name: str) -> str | None:
    match = re.search(rf"""{name}\s*=\s*["']([^"']+)["']""", tag, re.I)
    return match.group(1) if match else None


def _images_from_html(html: str | None) -> list[dict[str, Any]]:
    if not html:
        return []
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tag in IMG_TAG_RE.findall(html):
        src = _html_attr(tag, "src") or _html_attr(tag, "data-src")
        if not src or src.startswith("data:") or src in seen:
            continue
        seen.add(src)
        images.append(
            {
                "url": src,
                "alt": _html_attr(tag, "alt") or "",
                "section": "Photos" if (_html_attr(tag, "alt") or "").strip().lower() == "photos" else "",
                "className": _html_attr(tag, "class") or "",
            }
        )
    return images


def _is_offer_asset(url: str) -> bool:
    lowered = url.lower()
    return any(hint in lowered for hint in OFFER_IMAGE_HINTS)


def _offer_urls_from_sources(html: str | None, dom_images: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str | None, section: str = "") -> None:
        if not url or url in seen or _looks_like_ui_image(url):
            return
        if _is_offer_asset(url) or "offer" in (section or "").lower():
            seen.add(url)
            urls.append(url)

    for item in dom_images or []:
        if isinstance(item, dict):
            add(item.get("url") if isinstance(item.get("url"), str) else None, item.get("section") or "")
    for item in _images_from_html(html):
        add(item.get("url"), item.get("section") or "")
    if html:
        for url in re.findall(r"https://(?:dineout-media-assets|media-assets)\.swiggy\.com/[^\"'\\s>]+", html):
            add(url)
    return urls


def _assign_offer_images(
    venue: DineoutVenue,
    html: str | None,
    dom_images: list[dict[str, Any]] | None,
) -> None:
    unused = [url for url in _offer_urls_from_sources(html, dom_images) if not _looks_like_ui_image(url)]
    for offer in venue.offers:
        current = offer.get("image")
        if isinstance(current, str) and current:
            unused = [url for url in unused if url != current]
            continue
        if unused:
            offer["image"] = unused.pop(0)


def _popular_from_html(html: str | None) -> list[str]:
    if not html:
        return []
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"[ \t]+", " ", text)
    match = re.search(r"Popular dishes\s+(.+?)\s+Cuisines\b", text, re.I | re.S)
    if not match:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for line in match.group(1).split("\n"):
        name = re.sub(r"\s+", " ", line).strip(" •·,-")
        if not name or "http" in name.lower() or len(name) > 80:
            continue
        if name.lower() in {"popular dishes", "menu", "photos"}:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _is_carousel_venue_photo(alt: str, class_name: str = "") -> bool:
    if SLIDE_ALT_RE.match((alt or "").strip()):
        return True
    if (alt or "").strip().lower() == "photos":
        return True
    cls = re.sub(r"[^a-z0-9]", "", (class_name or "").lower())
    if "menusection" in cls or "menucard" in cls:
        return False
    return "imagecarousel" in cls or "photowidget" in cls


def _classify_image(
    url: str,
    alt: str = "",
    section: str = "",
    restaurant_id: str | None = None,
    venue_name: str | None = None,
    class_name: str = "",
) -> str | None:
    if not url or _looks_like_ui_image(url):
        return None
    if any(hint in (section or "").lower() for hint in RECOMMENDATION_HINTS):
        return None
    lowered_alt = (alt or "").strip().lower()
    lowered_url = url.lower()
    lowered_section = (section or "").lower()
    if _is_offer_asset(url) or "offer" in lowered_section:
        return "offer"
    if "map" in lowered_url or "staticmap" in lowered_url or lowered_alt in {"map", "location"}:
        return "map"
    if lowered_alt in MENU_IMAGE_ALTS or "menu" in (section or "").lower() or _looks_like_menu_asset(url):
        return "menu"
    if lowered_alt == "ambience" or "ambience" in lowered_alt:
        return "hero"
    venue_photo = any(
        token in lowered_alt for token in ("interior", "outdoor", "seating", "dining", "entrance", "decor", "venue")
    )
    dineout_asset = "dineout-media-assets" in lowered_url or "media-assets.swiggy" in lowered_url
    belongs_to_venue = bool(restaurant_id) and restaurant_id in url
    if venue_photo or belongs_to_venue:
        return "gallery"
    if venue_name and alt and _names_match(alt, venue_name):
        return "gallery"
    if _is_carousel_venue_photo(alt, class_name):
        return "gallery"
    if "photo" in lowered_section or lowered_section.strip() in {"photos", "gallery"}:
        return "gallery"
    if dineout_asset and "restaurant_image_service" in lowered_url:
        return "gallery"
    return None


def _apply_classified_images(
    venue: DineoutVenue,
    html: str | None,
    dom_images: list[dict[str, Any]] | None,
) -> None:
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(dom_images or []) + _images_from_html(html):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        collected.append(item)
    buckets: dict[str, list[dict[str, Any]]] = {"hero": [], "gallery": [], "menu": [], "map": [], "offer": []}
    for item in collected:
        kind = _classify_image(
            item.get("url") or "",
            item.get("alt") or "",
            item.get("section") or "",
            venue.restaurant_id,
            venue.venue,
            item.get("className") or item.get("class") or "",
        )
        if kind:
            buckets[kind].append(item)
    if buckets["hero"]:
        venue.hero_image = buckets["hero"][0]["url"]
    elif not venue.hero_image and buckets["gallery"]:
        venue.hero_image = buckets["gallery"][0]["url"]
    gallery = list(venue.gallery_images or [])
    gallery_seen = {item.get("url") for item in gallery}
    for item in buckets["hero"] + buckets["gallery"]:
        url = item["url"]
        if url in gallery_seen:
            continue
        gallery_seen.add(url)
        entry: dict[str, Any] = {"url": url}
        alt = (item.get("alt") or "").strip().lower()
        if alt == "ambience" or "ambience" in alt or "interior" in alt:
            entry["category"] = "ambience"
        gallery.append(entry)
    if venue.hero_image:
        gallery.sort(key=lambda item: 0 if item.get("url") == venue.hero_image else 1)
    venue.gallery_images = gallery
    venue.photos = [item["url"] for item in gallery if item.get("url")]
    if not venue.location_map_image and buckets["map"]:
        raw_map = buckets["map"][0]["url"]
        coords = _coords_from_url(raw_map)
        if coords:
            venue.location_map_image = _static_map_url(coords[0], coords[1])
            maps_link = f"https://www.google.com/maps?q={coords[0]},{coords[1]}"
            if isinstance(venue.location, dict):
                venue.location["map_image"] = venue.location_map_image
                venue.location["maps_url"] = venue.location.get("maps_url") or maps_link
        elif raw_map.startswith("http") and not raw_map.startswith("https://maps.google"):
            venue.location_map_image = raw_map
            if isinstance(venue.location, dict):
                venue.location["map_image"] = venue.location_map_image
    existing_menu: dict[str, dict[str, Any]] = {page["title"].casefold(): page for page in venue.menu_pages if page.get("title")}
    for item in buckets["menu"]:
        url = item["url"]
        title = (item.get("alt") or "Menu").strip() or "Menu"
        page = existing_menu.get(title.casefold())
        if page:
            images = list(page.get("images") or ([page["image"]] if page.get("image") else []))
            if _image_filename(url) not in {_image_filename(image) for image in images}:
                images.append(url)
                page["images"] = images
                page["image"] = images[0]
                page["page_count"] = page.get("page_count") or len(images)
            continue
        page = {"title": title, "image": url, "images": [url], "identity": url, "page_count": 1}
        venue.menu_pages.append(page)
        existing_menu[title.casefold()] = page
    venue.menu_pages = _collapse_menu_pages(venue.menu_pages)


def _extract_amenities(extra: dict[str, Any], nodes: list[dict[str, Any]], info: dict[str, Any] | None = None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = value.strip() if isinstance(value, str) else None
        if isinstance(value, dict):
            text = _first_str(value.get("name"), value.get("title"), value.get("text"), value.get("label"))
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        names.append(text)

    for key in ("amenities", "facilities", "attributes", "highlights"):
        value = extra.get(key)
        if isinstance(value, list):
            for item in value:
                add(item)
        else:
            add(value)
    if isinstance(info, dict):
        for key in ("highlights", "amenities", "facilities", "vendorHighlights"):
            value = info.get(key)
            if isinstance(value, list):
                for item in value:
                    add(item)
    for node in nodes:
        type_name = _type_name(node).lower()
        title = _first_str(node.get("title"), node.get("header")) or ""
        if "amenit" not in type_name and "facilit" not in type_name and "amenit" not in title.lower():
            continue
        is_section = bool(re.match(r"amenities(?:\s*\(\d+\))?$", title.lower().strip()))
        if not is_section:
            add(node)
        items = node.get("amenities") or node.get("items") or node.get("info")
        if isinstance(items, list):
            for item in items:
                add(item)
    return names


def _extract_popular_dishes(extra: dict[str, Any], nodes: list[dict[str, Any]], info: dict[str, Any] | None = None) -> list[str]:
    dishes: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = value.strip() if isinstance(value, str) else None
        if isinstance(value, dict):
            text = _first_str(value.get("name"), value.get("title"))
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        dishes.append(text)

    for key in ("topDishes", "popularDishes", "mustTry", "famousDishes"):
        value = extra.get(key)
        if isinstance(value, str):
            for part in value.split(","):
                add(part)
        elif isinstance(value, list):
            for item in value:
                add(item)
    if isinstance(info, dict):
        for key in ("topDishes", "popularDishes", "mustTry", "famousDishes"):
            value = info.get(key)
            if isinstance(value, str):
                for part in value.split(","):
                    add(part)
            elif isinstance(value, list):
                for item in value:
                    add(item)
    for node in nodes:
        type_name = _type_name(node).lower()
        title = (_first_str(node.get("title"), node.get("header")) or "").lower()
        if "populardish" not in type_name and "musttry" not in type_name and "popular dish" not in title:
            continue
        items = node.get("items") or node.get("dishes")
        if isinstance(items, list):
            for item in items:
                add(item)
    return dishes


def _opening_hours(info: dict[str, Any], extra: dict[str, Any]) -> str | None:
    for source in (info.get("availability"), extra.get("availability")):
        if isinstance(source, dict):
            text = _first_str(source.get("nextCloseTime"), source.get("opened"), source.get("message"), source.get("displayTime"))
            if text:
                return text
    return None


def _phone(info: dict[str, Any], extra: dict[str, Any], nodes: list[dict[str, Any]]) -> str | None:
    for source in (info, extra):
        for key in ("phone", "mobile", "contactNumber", "phoneNumber"):
            found = _first_str(source.get(key))
            if found:
                return found
    for node in nodes:
        type_name = _type_name(node).lower()
        if "contact" not in type_name and "call" not in type_name and "phone" not in type_name:
            continue
        found = _first_str(node.get("phone"), node.get("phoneNumber"), node.get("mobile"), node.get("text"))
        if found and any(ch.isdigit() for ch in found):
            return found
    return None


def _map_url(info: dict[str, Any], extra: dict[str, Any], nodes: list[dict[str, Any]]) -> str | None:
    for source in (info, extra, extra.get("address_raw") if isinstance(extra.get("address_raw"), dict) else {}):
        for key in ("mapUrl", "googleMapsUrl", "directionUrl", "mapsUrl", "ctaUrl"):
            found = _first_str(source.get(key) if isinstance(source, dict) else None)
            if found and found.startswith("http"):
                return found
    for node in nodes:
        type_name = _type_name(node).lower()
        title = (_first_str(node.get("title"), node.get("cta", {}).get("text") if isinstance(node.get("cta"), dict) else None) or "").lower()
        if "direction" not in type_name and "map" not in type_name and title not in {"directions", "direction"}:
            continue
        found = _first_str(
            node.get("mapUrl"),
            node.get("googleMapsUrl"),
            node.get("directionUrl"),
            node.get("link"),
            node.get("url"),
            node.get("cta", {}).get("link") if isinstance(node.get("cta"), dict) else None,
        )
        if found and found.startswith("http"):
            return found
    return None


def _map_image(nodes: list[dict[str, Any]]) -> str | None:
    for node in nodes:
        type_name = _type_name(node).lower()
        title = (_first_str(node.get("title"), node.get("header")) or "").lower()
        if "map" not in type_name and title not in {"location", "map"}:
            continue
        images = _collect_images(node)
        if images:
            return images[0]
    return None


def _location(restaurant: Restaurant, extra: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    location: dict[str, Any] = {}
    address = _first_str(info.get("address"), restaurant.address)
    if address:
        location["address"] = address
        location["location"] = address
    locality = _first_str(info.get("locality"), info.get("areaName"), extra.get("locality"), extra.get("areaName"))
    city = _first_str(info.get("city"), extra.get("city"))
    if locality and city and locality.lower() != city.lower():
        location["locality"] = f"{locality}, {city}"
        location["outlet"] = f"{locality}, {city}"
    elif locality:
        location["locality"] = locality
        location["outlet"] = locality
    if city:
        location["city"] = city
    if restaurant.outlet and "outlet" not in location:
        location["outlet"] = restaurant.outlet
    return location


def _extract_videos(html: str | None) -> list[dict[str, Any]]:
    if not html:
        return []
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"""<(?:video|source)\b[^>]*src=["']([^"']+\.(?:mp4|webm|mov|m3u8)[^"']*)["']""",
        html,
        re.I,
    ):
        url = match.group(1).strip()
        key = url.split("?")[0].lower()
        if not url or key in seen:
            continue
        seen.add(key)
        found.append({"source_url": url})
    return found


def _dedupe_videos(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("source_url") or item.get("url") or "").strip()
        key = url.split("?")[0].lower()
        if not url or key in seen:
            continue
        seen.add(key)
        unique.append({"source_url": url, **{k: v for k, v in item.items() if k not in {"source_url", "url"} or v}})
    return unique


def _to_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value in (None, "", "--"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return number
