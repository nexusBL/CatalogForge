from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from scraper.swiggy.chrome_session import (
    ChromeHandle,
    ChromeUnavailableError,
    acquire_chrome,
    acquire_chrome_background,
    acquire_chrome_cdp,
    close_chrome,
    resolve_browser_mode,
)
from scraper.swiggy.models import RawSource

NAV_TIMEOUT_MS = 45_000
MENU_WAIT_MS = 20_000
CHALLENGE_WAIT_MS = 12_000
TEXT_LIMIT = 2_000
HTML_DIAG_LIMIT = 8_000
MAX_SCROLL_STEPS = 16
SCROLL_STABLE_ROUNDS = 3

MENU_URL_HINTS = (
    "dapi/menu",
    "mapi/menu",
    "/menu/pl",
    "complete-menu",
    "REGULAR_MENU",
)

JSON_URL_HINTS = MENU_URL_HINTS + (
    "dapi/restaurants",
    "mapi/restaurants",
    "menu/v4",
    "menu/v5",
    "menu/pl",
    "itemcollection",
    "catalog/menu",
    "dineout",
    "dining",
)

RELEVANT_HEADERS = (
    "x-amzn-waf-action",
    "x-cache",
    "x-amz-cf-id",
    "x-amz-cf-pop",
    "server",
    "via",
    "content-type",
    "content-length",
    "cache-control",
    "retry-after",
    "location",
    "cf-ray",
    "access-control-allow-origin",
)

CITY_COORDS = {
    "mangaluru": (12.914141, 74.855957),
    "mangalore": (12.914141, 74.855957),
}


def collect_local_source(
    source_url: str,
    json_path: str | Path | None = None,
    html_path: str | Path | None = None,
) -> RawSource:
    """Load previously saved HTML/JSON instead of contacting Swiggy."""
    raw = RawSource(source_url=source_url, final_url=source_url, http_status=200)
    locations: list[str] = []
    if json_path:
        payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
        raw.api_payloads = [payload]
        locations.append(f"local_json:{json_path}")
    if html_path:
        html = Path(html_path).read_text(encoding="utf-8")
        raw.html = html
        raw.page_title = _title_from_html(html)
        raw.page_text = _text_from_html(html)
        raw.next_data = _extract_next_data(html)
        raw.json_ld = _extract_json_ld(html)
        locations.append(f"local_html:{html_path}")
        if raw.next_data:
            locations.append("embedded_json:__NEXT_DATA__")
        if raw.json_ld:
            locations.append("json_ld")
    raw.data_locations = locations
    raw.blocked = False
    raw.access_status = "ok"
    return raw


def collect_swiggy_source(
    url: str,
    diagnostic_dir: str | Path | None = None,
    browser_mode: str | None = None,
) -> RawSource:
    raw = RawSource(source_url=url)
    mode = resolve_browser_mode(browser_mode)
    raw.browser_mode = mode
    handle: ChromeHandle | None = None
    try:
        with sync_playwright() as playwright:
            try:
                handle = _open_browser(playwright, mode)
            except ChromeUnavailableError as exc:
                raw.access_status = "failed"
                raw.blocked = False
                raw.reason = str(exc)
                raw.browser_path = exc.path
                if diagnostic_dir:
                    save_diagnostics(raw, diagnostic_dir)
                return raw
            raw.browser_path = handle.path
            raw.browser_mode = handle.mode
            browser = handle.browser
            if handle.mode in {"chrome-cdp", "chrome", "chrome-background"}:
                context, page = _existing_or_new_page(browser, url)
            else:
                context = _new_context(browser, url)
                page = context.new_page()
            payloads: list[Any] = []
            network_urls: list[str] = []
            captured_headers: dict[str, str] = {}
            waf_action: str | None = None
            http_status: int | None = None
            data_locations: list[str] = []

            def on_response(response) -> None:
                nonlocal waf_action, http_status
                response_url = response.url
                network_urls.append(response_url)
                headers = response.headers or {}
                header_action = headers.get("x-amzn-waf-action")
                if header_action:
                    waf_action = header_action
                request = response.request
                is_document = request.resource_type == "document" and _same_origin_path(url, response_url)
                if is_document:
                    http_status = response.status
                    captured_headers.update(_pick_headers(headers))
                content_type = headers.get("content-type", "")
                if _looks_like_app_json(response_url, content_type):
                    body = _safe_json(response)
                    if body is not None and _keep_json_payload(response_url, body):
                        payloads.append(body)
                        data_locations.append(f"xhr:{response_url.split('?')[0]}")

            page.on("response", on_response)

            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except PlaywrightTimeout:
                raw.access_status = "failed"
                raw.blocked = False
                raw.reason = f"Navigation timed out after {NAV_TIMEOUT_MS}ms"
                _apply_capture(raw, http_status, waf_action, captured_headers, network_urls, payloads, data_locations)
                _fill_page_diagnostics(raw, page, diagnostic_dir)
                close_chrome(handle)
                return raw
            except Exception:
                raw.access_status = "blocked" if _is_block_status(http_status, waf_action) else "failed"
                raw.blocked = raw.access_status == "blocked"
                raw.reason = _block_reason(http_status, waf_action) if raw.blocked else (
                    f"Restaurant page could not be loaded (HTTP {http_status})."
                )
                _apply_capture(raw, http_status, waf_action, captured_headers, network_urls, payloads, data_locations)
                try:
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
                _fill_page_diagnostics(raw, page, diagnostic_dir)
                close_chrome(handle)
                return raw

            if response is not None:
                http_status = response.status
                captured_headers.update(_pick_headers(response.headers or {}))
                header_action = (response.headers or {}).get("x-amzn-waf-action")
                if header_action:
                    waf_action = header_action

            # Let a normal challenge/page continue rendering. Do not retry-storm.
            try:
                page.wait_for_load_state("load", timeout=NAV_TIMEOUT_MS)
            except Exception:
                pass

            challenged = _is_block_status(http_status, waf_action)
            if http_status in {401, 403} or (page.url or "").startswith("chrome-error://"):
                if not payloads:
                    raw.final_url = page.url
                    raw.access_status = "blocked"
                    raw.blocked = True
                    raw.reason = _block_reason(http_status, waf_action)
                    _apply_capture(raw, http_status, waf_action, captured_headers, network_urls, payloads, data_locations)
                    _fill_page_diagnostics(raw, page, diagnostic_dir)
                    close_chrome(handle)
                    return raw
            if challenged:
                page.wait_for_timeout(CHALLENGE_WAIT_MS)
                try:
                    page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass
                if not payloads:
                    _wait_for_menu_network(page)
                    _wait_for_client_menu(page)
                if not payloads and (
                    _is_block_status(http_status, waf_action) or (page.url or "").startswith("chrome-error://")
                ):
                    raw.final_url = page.url
                    raw.access_status = "blocked"
                    raw.blocked = True
                    raw.reason = _block_reason(http_status, waf_action)
                    _apply_capture(raw, http_status, waf_action, captured_headers, network_urls, payloads, data_locations)
                    _fill_page_diagnostics(raw, page, diagnostic_dir)
                    close_chrome(handle)
                    return raw
            elif not payloads:
                _wait_for_client_menu(page)

            gallery_photos: list[dict[str, Any]] = []
            if not _is_block_status(http_status, waf_action) and not (page.url or "").startswith("chrome-error://"):
                _scroll_for_lazy_menu(page)
                if not payloads:
                    _wait_for_menu_network(page)
                    _wait_for_client_menu(page)
                if "dineout" in (url or "").lower():
                    gallery_photos = _open_dineout_image_gallery(page)
                else:
                    from scraper.gallery_walk import open_interactive_gallery, should_traverse_gallery

                    if should_traverse_gallery(page.url or url):
                        gallery_photos = open_interactive_gallery(page)
                from scraper.platform_dom import platform_from_url, wait_for_platform_menu

                if platform_from_url(page.url or url):
                    wait_for_platform_menu(page, page.url or url)
                    _scroll_for_lazy_menu(page)

            html = None
            try:
                html = page.content()
            except Exception:
                html = None

            embedded = _read_embedded_state(page)
            from scraper.platform_dom import harvest_platform_menu, platform_from_url

            platform_menu = harvest_platform_menu(page, page.url or url) if platform_from_url(page.url or url) else {}
            if gallery_photos:
                seen_keys = {_photo_file_key(item.get("url") or "") for item in gallery_photos if isinstance(item, dict)}
                rest = [
                    item
                    for item in (embedded.get("dom_images") or [])
                    if isinstance(item, dict)
                    and _photo_file_key(item.get("url") or "") not in seen_keys
                ]
                embedded["dom_images"] = [*gallery_photos, *rest]
            if embedded.get("next_data"):
                data_locations.append("embedded_json:__NEXT_DATA__")
            if embedded.get("json_ld"):
                data_locations.append("json_ld")
            if embedded.get("window_state"):
                payloads.append(embedded["window_state"])
                data_locations.append("window_state")
            if embedded.get("dom_menu"):
                raw.dom_menu = embedded["dom_menu"]
                data_locations.append("dom")
            if platform_menu.get("dom_menu"):
                raw.dom_menu = platform_menu["dom_menu"]
                data_locations.append("platform_dom_menu")
            if embedded.get("dom_images"):
                raw.dom_images = embedded["dom_images"]
                data_locations.append("dom_images")
            if platform_menu.get("dom_images"):
                raw.dom_images = list(raw.dom_images or []) + [
                    item for item in platform_menu["dom_images"] if isinstance(item, dict)
                ]
                data_locations.append("platform_dom_images")
            if embedded.get("map_embed"):
                raw.dom_images = list(raw.dom_images or []) + [
                    {"url": embedded["map_embed"], "alt": "Location", "section": "Location"}
                ]
                data_locations.append("dom_map")
            data_locations.extend(embedded.get("dom_hints") or [])

            raw.final_url = page.url
            raw.http_status = http_status
            raw.html = html
            raw.next_data = embedded.get("next_data") or _extract_next_data(html)
            raw.json_ld = embedded.get("json_ld") or _extract_json_ld(html)
            raw.api_payloads = payloads
            raw.network_urls = network_urls[:200]
            raw.waf_action = waf_action
            raw.response_headers = captured_headers
            raw.window_state_keys = embedded.get("window_keys") or []
            raw.data_locations = list(dict.fromkeys(data_locations))
            status, reason = _access_state(
                url=page.url,
                http_status=http_status,
                waf_action=waf_action,
                html=html,
                payloads=payloads,
                next_data=raw.next_data,
                json_ld=raw.json_ld,
                dom_menu=raw.dom_menu,
            )
            raw.access_status = status
            raw.blocked = status == "blocked"
            raw.reason = reason
            if status != "ok":
                _fill_page_diagnostics(raw, page, diagnostic_dir)
            else:
                _fill_page_diagnostics(raw, page, None)
            close_chrome(handle)
            return raw
    except Exception as exc:
        raw.access_status = "failed"
        raw.blocked = False
        raw.reason = f"Browser/session failed: {type(exc).__name__}: {exc}"
        close_chrome(handle)
        return raw


def _apply_capture(
    raw: RawSource,
    http_status: int | None,
    waf_action: str | None,
    captured_headers: dict[str, str],
    network_urls: list[str],
    payloads: list[Any],
    data_locations: list[str],
) -> None:
    raw.http_status = http_status
    raw.waf_action = waf_action
    raw.response_headers = captured_headers
    raw.network_urls = network_urls[:200]
    raw.api_payloads = payloads
    raw.data_locations = list(dict.fromkeys(data_locations))


def save_diagnostics(raw: RawSource, diagnostic_dir: str | Path) -> Path:
    dest = Path(diagnostic_dir)
    dest.mkdir(parents=True, exist_ok=True)
    excerpt = (raw.html or "")[:HTML_DIAG_LIMIT]
    payload = {
        "source_url": raw.source_url,
        "final_url": raw.final_url,
        "http_status": raw.http_status,
        "waf_action": raw.waf_action,
        "reason": raw.reason,
        "blocked": raw.blocked,
        "page_title": raw.page_title,
        "response_headers": raw.response_headers,
        "window_state_keys": raw.window_state_keys,
        "data_locations": raw.data_locations,
        "network_urls_sample": raw.network_urls[:40],
        "page_text": raw.page_text,
        "html_excerpt": excerpt,
        "screenshot_path": raw.screenshot_path,
        "dom_discovery": raw.dom_discovery,
        "browser_mode": raw.browser_mode,
        "browser_path": raw.browser_path,
        "page_status": raw.http_status,
    }
    (dest / "diagnostics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "page_text.txt").write_text(raw.page_text or "", encoding="utf-8")
    if raw.dom_discovery:
        (dest / "dom_discovery.json").write_text(
            json.dumps(raw.dom_discovery, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return dest


def _open_browser(playwright, mode: str) -> ChromeHandle:
    if mode == "chrome-cdp":
        return acquire_chrome_cdp(playwright)
    if mode == "chrome":
        return acquire_chrome(playwright)
    if mode == "chrome-background":
        return acquire_chrome_background(playwright)
    browser = _launch_browser(playwright)
    return ChromeHandle(
        browser=browser,
        mode="playwright",
        path=None,
        debug_url=None,
        owns_browser=True,
    )


def _existing_or_new_page(browser, url: str):
    contexts = list(getattr(browser, "contexts", []) or [])
    if contexts:
        context = contexts[0]
        pages = list(getattr(context, "pages", []) or [])
        page = pages[-1] if pages else context.new_page()
        return context, page
    context = _new_context(browser, url)
    return context, context.new_page()


def _launch_browser(playwright):
    try:
        return playwright.chromium.launch(headless=True, channel="chrome")
    except Exception:
        return playwright.chromium.launch(headless=True)


def _new_context(browser, url: str):
    kwargs: dict[str, Any] = {
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "viewport": {"width": 1366, "height": 768},
        "extra_http_headers": {"Accept-Language": "en-IN,en;q=0.9"},
    }
    coords = _coords_for_url(url)
    if coords:
        kwargs["geolocation"] = {"latitude": coords[0], "longitude": coords[1]}
        kwargs["permissions"] = ["geolocation"]
    return browser.new_context(**kwargs)


def _coords_for_url(url: str) -> tuple[float, float] | None:
    path = urlparse(url).path.lower()
    for city, coords in CITY_COORDS.items():
        if f"/city/{city}/" in path or f"/{city}/" in path:
            return coords
    return None


def _scroll_for_lazy_menu(page) -> None:
    """Scroll a reachable page so lazily loaded menu sections/XHR can appear.

    Stops when page height/text stabilize, or the configured maximum is reached.
    Does not retry blocked/challenged documents or attempt to bypass access controls.
    """
    max_steps = int(os.getenv("CATALOGFORGE_SWIGGY_MAX_SCROLL", str(MAX_SCROLL_STEPS)))
    try:
        last_height = 0
        last_text_len = -1
        stable = 0
        for _ in range(max(1, max_steps)):
            metrics = page.evaluate(
                """() => ({
                    height: document.body ? document.body.scrollHeight : 0,
                    text: document.body && document.body.innerText ? document.body.innerText.length : 0
                })"""
            )
            height = int((metrics or {}).get("height") or 0)
            text_len = int((metrics or {}).get("text") or 0)
            page.evaluate("window.scrollBy(0, Math.max(window.innerHeight || 0, 700))")
            page.wait_for_timeout(280)
            if height <= last_height and text_len <= last_text_len:
                stable += 1
                if stable >= SCROLL_STABLE_ROUNDS:
                    break
            else:
                stable = 0
            last_height = max(last_height, height)
            last_text_len = max(last_text_len, text_len)
        if "dineout" not in (page.url or "").lower():
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(250)
    except Exception:
        pass


def _wait_for_menu_network(page) -> None:
    try:
        page.wait_for_response(
            lambda response: any(hint.lower() in (response.url or "").lower() for hint in MENU_URL_HINTS),
            timeout=MENU_WAIT_MS,
        )
    except Exception:
        pass


def _wait_for_client_menu(page) -> None:
    try:
        page.wait_for_timeout(1500)
        page.wait_for_function(
            """() => {
                const html = document.documentElement ? document.documentElement.innerHTML : '';
                const ready = document.readyState === 'complete';
                return ready && (
                    html.includes('__NEXT_DATA__')
                    || html.includes('cloudinaryImageId')
                    || html.includes('ITEM_CATEGORY')
                    || html.includes('application/ld+json')
                );
            }""",
            timeout=MENU_WAIT_MS,
        )
    except PlaywrightTimeout:
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass
    except Exception:
        pass


PHOTO_WIDGET_WAIT_MS = 20_000
PHOTO_SETTLE_MS = 3_000
SLIDE_SETTLE_MS = 2_200

_COLLECT_DINEOUT_PHOTOS_JS = """() => {
    const junk = /iconleft|iconright|cross\\.png|seo%20web|seo web|plus_icon|oneexclusive|marketing_banners|nba_rupees/i;
    const venue = /RESTAURANT_IMAGE_SERVICE|dineout-media-assets|media-assets\\.swiggy|swiggy\\.com\\/swiggy\\/image/i;
    const seen = new Set();
    const out = [];
    const srcOf = (img) => {
        const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset') || '';
        if (srcset) {
            const parts = srcset.split(',').map((part) => part.trim().split(' ')[0]).filter(Boolean);
            if (parts.length) return parts[parts.length - 1];
        }
        return img.currentSrc || img.getAttribute('src') || img.getAttribute('data-src') || '';
    };
    const fileKey = (src) => (src.split('/').pop() || src).split('?')[0].toLowerCase();
    const push = (img) => {
        const src = srcOf(img);
        if (!src || src.startsWith('data:') || junk.test(src) || !venue.test(src)) return;
        const key = fileKey(src);
        if (seen.has(key)) return;
        const alt = img.getAttribute('alt') || '';
        const cls = String(img.className || '');
        if (/MenuSectionWidget|MenuCard/i.test(cls)) return;
        const inOverlay = !!img.closest('[role="dialog"], [aria-modal="true"], [class*="modal" i], [class*="overlay" i], [class*="lightbox" i], [class*="gallery" i], [class*="slider" i], [class*="carousel" i], [class*="viewer" i], [class*="swiper" i]');
        const inPhotos = inOverlay || !!img.closest('#photos, [data-testid="rdp_photos_widget"], [class*="PhotoWidget"], [class*="PhotoGrid"]');
        const slide = /^slide\\s*\\d+/i.test(alt.trim());
        const photosAlt = alt.trim().toLowerCase() === 'photos';
        if (!(inPhotos || slide || photosAlt)) return;
        seen.add(key);
        out.push({ url: src, alt, section: 'Photos', className: cls });
    };
    document.querySelectorAll(
        '#photos img, [data-testid="rdp_photos_widget"] img, [class*="PhotoWidget__DesktopPhotoGrid"] img, [role="dialog"] img, [aria-modal="true"] img, [class*="modal" i] img, [class*="lightbox" i] img, img[alt="Photos"], img[alt^="Slide "]'
    ).forEach(push);
    return out;
}"""


def _photo_file_key(url: str) -> str:
    return (url or "").split("/")[-1].split("?")[0].lower()


def _harvest_dineout_photos(page) -> list[dict[str, Any]]:
    try:
        batch = page.evaluate(_COLLECT_DINEOUT_PHOTOS_JS) or []
    except Exception:
        return []
    return [item for item in batch if isinstance(item, dict) and item.get("url")]


def _wait_for_photo_widget(page) -> None:
    try:
        page.locator('#photos, [data-testid="rdp_photos_widget"]').first.scroll_into_view_if_needed(timeout=8_000)
    except Exception:
        try:
            page.evaluate(
                """() => {
                    const el = document.querySelector(
                        '#photos, [data-testid="rdp_photos_widget"], [class*="PhotoWidget__DesktopPhotoGridWrapper"]'
                    );
                    if (el) el.scrollIntoView({ block: 'center' });
                }"""
            )
        except Exception:
            pass
    try:
        page.wait_for_selector(
            '#photos img, [data-testid="rdp_photos_widget"] img, img[alt="Photos"]',
            timeout=PHOTO_WIDGET_WAIT_MS,
        )
    except Exception:
        pass
    try:
        page.wait_for_function(
            """() => {
                const nodes = document.querySelectorAll(
                    '#photos img, [data-testid="rdp_photos_widget"] img, img[alt="Photos"]'
                );
                let ready = 0;
                for (const img of nodes) {
                    const src = img.currentSrc || img.src || '';
                    if (img.complete && img.naturalWidth > 40 && /RESTAURANT_IMAGE_SERVICE/i.test(src)) {
                        ready += 1;
                    }
                }
                return ready >= 4;
            }""",
            timeout=PHOTO_WIDGET_WAIT_MS,
        )
    except Exception:
        pass
    try:
        page.wait_for_timeout(PHOTO_SETTLE_MS)
    except Exception:
        pass


def _click_visible(locator) -> bool:
    try:
        count = locator.count()
    except Exception:
        return False
    for index in range(count):
        item = locator.nth(index)
        try:
            if item.is_visible():
                item.click(timeout=5_000)
                return True
        except Exception:
            continue
    return False


def _open_dineout_image_gallery(page) -> list[dict[str, Any]]:
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()

    def harvest() -> None:
        for item in _harvest_dineout_photos(page):
            url = item.get("url")
            if not isinstance(url, str):
                continue
            key = _photo_file_key(url)
            if not key or key in seen:
                continue
            seen.add(key)
            photos.append(item)

    _wait_for_photo_widget(page)
    harvest()
    opened = _click_visible(page.get_by_text("Show all images", exact=True))
    if not opened:
        opened = _click_visible(page.get_by_text("Show all images", exact=False))
    if not opened:
        opened = _click_visible(page.get_by_text("View all images", exact=False))
    if not opened:
        opened = _click_visible(page.get_by_text("View all photos", exact=False))
    if not opened:
        opened = _click_visible(page.get_by_text("View Gallery", exact=False))
    if not opened:
        opened = _click_visible(page.locator('[aria-label="View photo 1"]'))
    if not opened:
        opened = _click_visible(
            page.get_by_role("button", name=re.compile(r"show all images|view all images|view all photos|view gallery|view photo\s*1", re.I))
        )
    if not opened:
        opened = _click_visible(page.locator('#photos img, [data-testid="rdp_photos_widget"] img').first)
    try:
        page.wait_for_selector(
            'button[aria-label*="Next" i], button[aria-label*="next" i], img[alt^="Slide "], [role="dialog"] img',
            timeout=PHOTO_WIDGET_WAIT_MS,
        )
    except Exception:
        pass
    try:
        page.wait_for_timeout(PHOTO_SETTLE_MS)
    except Exception:
        pass
    harvest()
    _advance_dineout_image_carousel(page, harvest, photos)
    return photos


def _advance_dineout_image_carousel(page, harvest=None, collected=None) -> None:
    next_btn_selectors = [
        page.get_by_role("button", name=re.compile(r"next slide|next image|next", re.I)),
        page.locator("button.carousel-button[aria-label='Next slide']"),
        page.locator('[aria-label*="Next" i], [aria-label*="next image" i], [aria-label*="right" i]'),
        page.locator('button:has-text("›"), button:has-text(">")'),
        page.locator('[class*="arrow" i][class*="right" i], [class*="rightArrow" i], [class*="next" i][class*="button" i], [class*="swiper-button-next" i]'),
        page.locator('[role="dialog"] button:has(svg), [aria-modal="true"] button:has(svg), .lightbox button:has(svg), [class*="modal" i] button:has(svg)'),
    ]

    total = 0
    try:
        total = int(
            page.evaluate(
                """() => {
                    const text = [...document.querySelectorAll('button,div,span,p')]
                        .map((el) => (el.textContent || '').trim())
                        .find((value) => /^\\d+\\s*\\/\\s*\\d+$/.test(value));
                    if (!text) return 0;
                    return parseInt(text.split('/')[1], 10) || 0;
                }"""
            )
            or 0
        )
    except Exception:
        total = 0
    steps = max(total or 0, 12)
    steps = min(steps, 200)
    clicked = 0
    stale = 0
    for _ in range(steps):
        before = len(collected) if collected is not None else None

        clicked_any = False
        for btn_locator in next_btn_selectors:
            if _click_visible(btn_locator):
                clicked_any = True
                break

        if not clicked_any:
            try:
                page.keyboard.press("ArrowRight")
                clicked_any = True
            except Exception:
                pass

        if not clicked_any:
            break

        clicked += 1
        try:
            page.wait_for_timeout(SLIDE_SETTLE_MS)
        except Exception:
            pass
        if harvest:
            harvest()

        if collected is not None and before is not None and len(collected) == before:
            stale += 1
            if stale >= 3:
                break
        else:
            stale = 0

        loaded = 0
        try:
            loaded = int(
                page.evaluate(
                    """() => {
                        const keys = new Set();
                        for (const img of document.querySelectorAll('img[alt^="Slide "], [role="dialog"] img, [aria-modal="true"] img')) {
                            const src = img.currentSrc || img.src || '';
                            if (!/RESTAURANT_IMAGE_SERVICE|dineout-media-assets|media-assets\\.swiggy/i.test(src)) continue;
                            keys.add((src.split('/').pop() || '').split('?')[0].toLowerCase());
                        }
                        return keys.size;
                    }"""
                )
                or 0
            )
        except Exception:
            loaded = 0
        if total and loaded >= total and clicked >= 1:
            break
    if harvest:
        harvest()


def _read_embedded_state(page) -> dict[str, Any]:
    try:
        return page.evaluate(
            """() => {
                const nextEl = document.getElementById('__NEXT_DATA__');
                let nextData = null;
                if (nextEl && nextEl.textContent) {
                    try { nextData = JSON.parse(nextEl.textContent); } catch (e) {}
                }
                const jsonLd = [];
                for (const el of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try { jsonLd.push(JSON.parse(el.textContent)); } catch (e) {}
                }
                const windowKeys = Object.keys(window).filter((key) =>
                    /state|STORE|swiggy|__NEXT|INITIAL|REDUX|APP_DATA/i.test(key)
                );
                let windowState = null;
                for (const key of ['__NEXT_DATA__', '__PRELOADED_STATE__', '__INITIAL_STATE__']) {
                    if (window[key] && typeof window[key] === 'object') {
                        windowState = window[key];
                        break;
                    }
                }
                const bodyText = (document.body && document.body.innerText) ? document.body.innerText : '';
                const domHints = [];
                if (document.querySelector('[data-testid], [class*="menu"], [class*="Menu"]')) {
                    domHints.push('dom:menu-like-nodes');
                }
                const domMenu = [];
                for (const section of document.querySelectorAll('[data-menu-category], section')) {
                    const heading = section.getAttribute('data-menu-category')
                        || (section.querySelector('h1,h2,h3') && section.querySelector('h1,h2,h3').textContent);
                    if (!heading) continue;
                    const items = [];
                    for (const row of section.querySelectorAll('[data-menu-item], article, li')) {
                        const itemName = row.getAttribute('data-menu-item')
                            || (row.querySelector('h3,h4,[data-item-name]') && row.querySelector('h3,h4,[data-item-name]').textContent);
                        if (!itemName) continue;
                        const img = row.querySelector('img');
                        const descAttr = row.getAttribute('data-description')
                            || (row.querySelector('[data-description]') && row.querySelector('[data-description]').getAttribute('data-description'));
                        const priceAttr = row.getAttribute('data-price')
                            || (row.querySelector('[data-price]') && row.querySelector('[data-price]').getAttribute('data-price'));
                        const foodType = row.getAttribute('data-food-type')
                            || row.getAttribute('data-veg-classifier');
                        const label = row.getAttribute('data-item-label');
                        items.push({
                            name: itemName.trim(),
                            description: descAttr || null,
                            price: priceAttr || null,
                            image_url: img ? (img.getAttribute('src') || img.getAttribute('data-src')) : null,
                            food_type: foodType || null,
                            labels: label ? [label] : [],
                        });
                    }
                    if (items.length) {
                        domMenu.push({ name: heading.trim(), items });
                    }
                }
                const rec = /recommended|near |nearby|brands near|more american|more restaurants|similar restaurant|explore more/i;
                const asset = /dineout-media-assets|media-assets.swiggy|swiggy.com\\/swiggy\\/image|RESTAURANT_IMAGE_SERVICE/i;
                function imageUrl(img) {
                    const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset') || '';
                    if (srcset) {
                        const parts = srcset.split(',').map((part) => part.trim().split(' ')[0]).filter(Boolean);
                        if (parts.length) return parts[parts.length - 1];
                    }
                    return img.currentSrc || img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
                }
                const domImages = [];
                const seen = new Set();
                function pushImage(img, sectionHint) {
                    const src = imageUrl(img);
                    if (!src || src.startsWith('data:') || seen.has(src)) return;
                    if (!asset.test(src)) return;
                    let section = sectionHint || '';
                    let el = img.parentElement;
                    for (let i = 0; i < 10 && el && !section; i++) {
                        const heading = el.querySelector('h1,h2,h3,h4');
                        const text = (heading && heading.textContent) || el.getAttribute('aria-label') || '';
                        if (text && text.trim().length > 2) { section = text.trim(); break; }
                        el = el.parentElement;
                    }
                    if (rec.test(section)) return;
                    if (/iconleft|iconright|cross\\.png|seo%20web|seo web/i.test(src)) return;
                    seen.add(src);
                    domImages.push({
                        url: src,
                        alt: img.getAttribute('alt') || '',
                        section: section.slice(0, 80),
                        className: String(img.className || ''),
                    });
                }
                for (const img of document.querySelectorAll('#photos img, [data-testid="rdp_photos_widget"] img, [class*="PhotoWidget__DesktopPhotoGrid"] img, [aria-label^="View photo"] img, img[alt="Photos"], img[alt^="Slide "]')) {
                    pushImage(img, 'Photos');
                }
                for (const img of document.querySelectorAll('img')) {
                    pushImage(img, '');
                }
                const mapFrame = document.querySelector('iframe[src*="google.com/maps"], iframe[src*="maps.google"]');
                const map_embed = mapFrame ? (mapFrame.getAttribute('src') || '') : '';
                return {
                    next_data: nextData,
                    json_ld: jsonLd,
                    window_keys: windowKeys.slice(0, 40),
                    window_state: windowState,
                    title: document.title || null,
                    text: bodyText.slice(0, 2000),
                    dom_hints: domHints,
                    dom_menu: domMenu,
                    dom_images: domImages.slice(0, 240),
                    map_embed: map_embed || null,
                };
            }"""
        )
    except Exception:
        return {}


def _fill_page_diagnostics(raw: RawSource, page, diagnostic_dir: str | Path | None) -> None:
    try:
        raw.page_title = page.title()
    except Exception:
        raw.page_title = raw.page_title or None
    try:
        raw.final_url = page.url
    except Exception:
        pass
    if not raw.page_text:
        try:
            raw.page_text = (page.inner_text("body") or "")[:TEXT_LIMIT]
        except Exception:
            if raw.html:
                raw.page_text = _text_from_html(raw.html)
    if diagnostic_dir is None:
        return
    dest = Path(diagnostic_dir)
    dest.mkdir(parents=True, exist_ok=True)
    screenshot = dest / "screenshot.png"
    try:
        page.screenshot(path=str(screenshot), full_page=False)
        raw.screenshot_path = str(screenshot)
    except Exception:
        raw.screenshot_path = None
    save_diagnostics(raw, dest)


def _pick_headers(headers: dict[str, str]) -> dict[str, str]:
    lowered = {str(k).lower(): v for k, v in headers.items()}
    return {key: lowered[key] for key in RELEVANT_HEADERS if key in lowered}


def _same_origin_path(original: str, response_url: str) -> bool:
    try:
        left = urlparse(original)
        right = urlparse(response_url)
        return left.netloc == right.netloc
    except Exception:
        return False


def _looks_like_app_json(url: str, content_type: str) -> bool:
    lowered = url.lower()
    if any(hint.lower() in lowered for hint in JSON_URL_HINTS):
        return True
    return "application/json" in content_type.lower() and any(
        host in lowered for host in ("swiggy.com", "zomato.com", "magicpin.in")
    )


def _keep_json_payload(url: str, body: Any) -> bool:
    lowered = url.lower()
    if any(hint.lower() in lowered for hint in JSON_URL_HINTS):
        return True
    return _has_menu_shape(body)


def _has_menu_shape(obj: Any, depth: int = 0) -> bool:
    if depth > 8 or obj is None:
        return False
    if isinstance(obj, dict):
        if any(key in obj for key in ("itemCards", "cardGroupMap", "groupedCard", "cloudinaryImageId")):
            return True
        type_name = str(obj.get("@type") or "")
        if "food.v2" in type_name or "ItemCategory" in type_name:
            return True
        for value in obj.values():
            if _has_menu_shape(value, depth + 1):
                return True
        return False
    if isinstance(obj, list):
        for item in obj[:40]:
            if _has_menu_shape(item, depth + 1):
                return True
    return False


def _safe_json(response) -> Any | None:
    try:
        return response.json()
    except Exception:
        try:
            text = response.text()
        except Exception:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None
    except BaseException:
        return None


def _extract_next_data(html: str | None) -> dict[str, Any] | None:
    if not html:
        return None
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _extract_json_ld(html: str | None) -> list[Any]:
    if not html:
        return []
    blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S | re.I)
    out = []
    for block in blocks:
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return out


def _title_from_html(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip() or None


def _text_from_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:TEXT_LIMIT]


def _is_block_status(http_status: int | None, waf_action: str | None) -> bool:
    return bool(waf_action) or http_status in {401, 403, 429, 202}


def _block_reason(http_status: int | None, waf_action: str | None) -> str:
    if waf_action:
        return (
            f"Swiggy/AWS WAF blocked access (action={waf_action}, HTTP {http_status}). "
            "No menu data was retrieved."
        )
    return (
        f"Swiggy/CloudFront denied the restaurant page (HTTP {http_status}). "
        "No menu data was retrieved."
    )


def _access_state(
    url: str,
    http_status: int | None,
    waf_action: str | None,
    html: str | None,
    payloads: list[Any],
    next_data: dict[str, Any] | None,
    json_ld: list[Any] | None = None,
    dom_menu: list[Any] | None = None,
) -> tuple[str, str | None]:
    has_structured = bool(payloads or next_data or json_ld or dom_menu)
    if _is_block_status(http_status, waf_action) or (url or "").startswith("chrome-error://"):
        if has_structured:
            return "ok", None
        return "blocked", _block_reason(http_status, waf_action)
    if has_structured:
        return "ok", None
    if html and ("awswaf" in html.lower() or "captcha" in html.lower()):
        return "blocked", "Page presented a bot/CAPTCHA challenge; extraction stopped."
    if not html or len(html) < 200:
        return "failed", f"Restaurant page returned no usable HTML (HTTP {http_status})."
    return "failed", "Page loaded but no restaurant/menu payload was found."
