"""Live scrape Brew 59 Magicpin delivery menu. Diagnostic only."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.magicpin.parser import delivery_menu_url, parse_magicpin_catalogue
from scraper.swiggy.scraper import collect_swiggy_source

STORE = "https://magicpin.in/Belgaum/Sadashiv-Nagar/Restaurant/Brew-59/store/606749"
OUT = Path("data/live-scrape-diagnostics")
OUT.mkdir(parents=True, exist_ok=True)


def summarize(label: str, raw) -> None:
    catalogue = parse_magicpin_catalogue(raw)
    items = [item.name for category in catalogue.categories for item in category.items]
    print(
        label,
        "status",
        catalogue.extraction_status,
        "cats",
        len(catalogue.categories),
        "items",
        catalogue.item_count,
        "named",
        len(items),
        "access",
        raw.access_status,
        "html",
        len(raw.html or ""),
        "text",
        len(raw.page_text or ""),
        "payloads",
        len(raw.api_payloads or []),
    )
    print(" names", items[:25])
    (OUT / f"{label}-meta.json").write_text(
        json.dumps(
            {
                "access_status": raw.access_status,
                "reason": raw.reason,
                "item_count": catalogue.item_count,
                "categories": [
                    {"name": c.name, "declared": c.item_count, "items": [i.name for i in c.items]}
                    for c in catalogue.categories
                ],
                "network_urls": (raw.network_urls or [])[:80],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (OUT / f"{label}-page.txt").write_text(raw.page_text or "", encoding="utf-8")
    (OUT / f"{label}.html").write_text((raw.html or "")[:400000], encoding="utf-8")


def main() -> None:
    store_raw = collect_swiggy_source(STORE, diagnostic_dir=OUT / "store")
    summarize("store", store_raw)
    delivery = delivery_menu_url(STORE)
    print("delivery url", delivery)
    if delivery:
        delivery_raw = collect_swiggy_source(delivery, diagnostic_dir=OUT / "delivery")
        summarize("delivery", delivery_raw)


if __name__ == "__main__":
    main()
