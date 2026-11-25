from __future__ import annotations

from typing import Any

from scraper.html_common import json_ld_nodes, restaurant_json_ld


def extract_zomato_place(html: str, extra: list[Any] | None = None) -> dict[str, Any]:
    """Cheap structured place from a Zomato HTML page. Does not scrape menus."""
    nodes = json_ld_nodes(html, extra)
    info = restaurant_json_ld(nodes) or {}
    address = info.get("address") if isinstance(info.get("address"), dict) else {}
    geo = info.get("geo") if isinstance(info.get("geo"), dict) else {}
    breadcrumbs: list[str] = []
    for node in nodes:
        types = node.get("@type")
        names = types if isinstance(types, list) else [types]
        if not any(str(name).lower() == "breadcrumblist" for name in names if name):
            continue
        for item in node.get("itemListElement") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                breadcrumbs.append(name.strip())
            nested = item.get("item")
            if isinstance(nested, dict) and isinstance(nested.get("name"), str):
                breadcrumbs.append(nested["name"].strip())
    lat = geo.get("latitude")
    lng = geo.get("longitude")
    try:
        latitude = float(lat) if lat not in (None, "") else None
    except (TypeError, ValueError):
        latitude = None
    try:
        longitude = float(lng) if lng not in (None, "") else None
    except (TypeError, ValueError):
        longitude = None
    return {
        "name": info.get("name") if isinstance(info.get("name"), str) else None,
        "street": address.get("streetAddress") if isinstance(address.get("streetAddress"), str) else None,
        "locality": address.get("addressLocality") if isinstance(address.get("addressLocality"), str) else None,
        "region": address.get("addressRegion") if isinstance(address.get("addressRegion"), str) else None,
        "postal_code": str(address["postalCode"]) if address.get("postalCode") not in (None, "") else None,
        "country": address.get("addressCountry") if isinstance(address.get("addressCountry"), str) else None,
        "latitude": latitude,
        "longitude": longitude,
        "breadcrumbs": breadcrumbs,
    }
