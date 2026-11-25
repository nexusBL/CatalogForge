from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scraper.magicpin.parser import (
    delivery_menu_url,
    merge_magicpin_images,
    merge_magicpin_menu,
    parse_magicpin_catalogue,
    photos_gallery_url,
)
from scraper.platform import DISPLAY, infer_legacy_platform, platform_url_error
from scraper.swiggy.chrome_session import resolve_browser_mode
from scraper.swiggy.parser import parse_swiggy_catalogue, restaurant_slug_from_url
from scraper.swiggy.scraper import collect_local_source, collect_swiggy_source, save_diagnostics
from scraper.zomato.parser import (
    merge_zomato_images,
    merge_zomato_menu,
    order_menu_url,
    parse_zomato_catalogue,
    photos_gallery_url as zomato_photos_url,
)


def _write_session_diagnostics(diagnostic_dir: Path, raw, catalogue) -> None:
    dest = Path(diagnostic_dir)
    dest.mkdir(parents=True, exist_ok=True)
    discovery = raw.dom_discovery or {}
    payload = {
        "browser_mode": raw.browser_mode,
        "browser_path": raw.browser_path,
        "final_url": raw.final_url,
        "page_title": raw.page_title,
        "page_status": raw.http_status,
        "blocked": raw.blocked,
        "candidate_lists": discovery.get("candidate_count"),
        "selected_candidate": discovery.get("selected_candidate"),
        "categories_found": len(catalogue.categories) if catalogue.extraction_status == "ok" else 0,
        "items_found": catalogue.item_count,
        "images_found": catalogue.image_count,
        "extraction_method": catalogue.source_type,
        "platform": catalogue.source,
        "catalogue_type": catalogue.catalogue_type,
    }
    (dest / "session.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_catalogue(raw, platform: str):
    if platform == "zomato":
        return parse_zomato_catalogue(raw)
    if platform == "magicpin":
        return parse_magicpin_catalogue(raw)
    return parse_swiggy_catalogue(raw)


def _output_slug(url: str) -> str:
    slug = restaurant_slug_from_url(url)
    if slug.lower() in {"order", "menu", "book", "photos", "dineout"}:
        parent = url.rstrip("/").rsplit("/", 1)[0]
        slug = restaurant_slug_from_url(parent)
    return slug


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a restaurant catalogue (Stage 1).")
    parser.add_argument("url", nargs="?", help="Restaurant URL")
    parser.add_argument(
        "--platform",
        choices=["swiggy", "zomato", "magicpin"],
        default=None,
        help="Platform adapter (default: inferred from URL, else swiggy)",
    )
    parser.add_argument(
        "--catalogue-type",
        dest="catalogue_type",
        choices=["restaurant", "dineout", "both"],
        default="restaurant",
        help="Catalogue type (default: restaurant)",
    )
    parser.add_argument(
        "--out-dir",
        default="output/swiggy",
        help="Directory for JSON output (default: output/swiggy)",
    )
    parser.add_argument(
        "--from-json",
        dest="from_json",
        help="Local JSON payload fixture (skips live browser access)",
    )
    parser.add_argument(
        "--from-html",
        dest="from_html",
        help="Local HTML fixture (skips live browser access)",
    )
    parser.add_argument(
        "--browser",
        choices=["playwright", "chrome", "chrome-background", "chrome-cdp", "visible", "background"],
        default=None,
        help="Browser mode: playwright, chrome (visible CDP), chrome-background, or chrome-cdp",
    )
    args = parser.parse_args(argv)

    url = (args.url or "").strip()
    local_mode = bool(args.from_json or args.from_html)
    if not local_mode and not url:
        parser.error("a restaurant URL is required unless --from-json/--from-html is used")
    if local_mode and not url:
        url = "https://www.swiggy.com/local-fixture"

    platform = infer_legacy_platform(url, args.platform)
    if not local_mode:
        mismatch = platform_url_error(platform, url)
        if mismatch:
            print(mismatch, file=sys.stderr)
            return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _output_slug(url)
    diagnostic_dir = out_dir / "diagnostics" / slug

    if local_mode:
        raw = collect_local_source(url, json_path=args.from_json, html_path=args.from_html)
        raw.browser_mode = "fixture"
    else:
        browser_mode = resolve_browser_mode(args.browser)
        raw = collect_swiggy_source(url, diagnostic_dir=diagnostic_dir, browser_mode=browser_mode)

    catalogue = _parse_catalogue(raw, platform)
    if not local_mode and catalogue.extraction_status == "ok":
        if platform == "magicpin":
            extra_url = delivery_menu_url(url)
            if extra_url and args.catalogue_type in {"restaurant", "both"}:
                extra_raw = collect_swiggy_source(
                    extra_url,
                    diagnostic_dir=diagnostic_dir / "delivery",
                    browser_mode=raw.browser_mode,
                )
                catalogue = merge_magicpin_menu(catalogue, parse_magicpin_catalogue(extra_raw))
            extra_url = photos_gallery_url(url)
            if extra_url:
                extra_raw = collect_swiggy_source(
                    extra_url,
                    diagnostic_dir=diagnostic_dir / "photos",
                    browser_mode=raw.browser_mode,
                )
                catalogue = merge_magicpin_images(catalogue, parse_magicpin_catalogue(extra_raw))
        elif platform == "zomato":
            extra_url = order_menu_url(url)
            if extra_url and args.catalogue_type in {"restaurant", "both"}:
                extra_raw = collect_swiggy_source(
                    extra_url,
                    diagnostic_dir=diagnostic_dir / "order",
                    browser_mode=raw.browser_mode,
                )
                catalogue = merge_zomato_menu(catalogue, parse_zomato_catalogue(extra_raw))
            extra_url = zomato_photos_url(url)
            if extra_url:
                extra_raw = collect_swiggy_source(
                    extra_url,
                    diagnostic_dir=diagnostic_dir / "photos",
                    browser_mode=raw.browser_mode,
                )
                catalogue = merge_zomato_images(catalogue, parse_zomato_catalogue(extra_raw))
    catalogue.catalogue_type = args.catalogue_type
    payload = catalogue.to_dict()
    payload["platform"] = platform
    payload["catalogue_type"] = args.catalogue_type
    if args.catalogue_type == "dineout":
        payload["categories"] = []
        payload["item_count"] = 0
    if catalogue.extraction_status != "ok" or raw.dom_discovery:
        payload["extraction"]["diagnostic_dir"] = str(diagnostic_dir)
        save_diagnostics(raw, diagnostic_dir)
        _write_session_diagnostics(diagnostic_dir, raw, catalogue)

    out_path = out_dir / f"{slug}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = catalogue.summary()
    print(f"Platform: {DISPLAY.get(platform, platform)}")
    print(f"Catalogue type: {args.catalogue_type}")
    print(f"Browser mode: {raw.browser_mode or 'playwright'}")
    print(f"Extraction status: {summary['extraction_status']}")
    print(f"Source type: {summary['source_type']}")
    print(f"Restaurant: {summary['restaurant']}")
    print(f"Categories found: {0 if args.catalogue_type == 'dineout' else summary['categories']}")
    print(f"Items found: {0 if args.catalogue_type == 'dineout' else summary['items']}")
    print(f"Images found: {summary['images']}")
    print(f"Saved: {out_path}")
    if catalogue.error:
        print(f"Error: {catalogue.error}")
    if raw.browser_mode == "chrome-cdp" and (raw.reason or "").startswith("CHROME_CDP_UNAVAILABLE"):
        print("CHROME_CDP_UNAVAILABLE")
        print("Start Chrome with remote debugging on port 9222 and try again.")
    if catalogue.extraction_status != "ok":
        print(f"Diagnostics: {diagnostic_dir}")
    return 0 if catalogue.extraction_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
