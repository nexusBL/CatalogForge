from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scraper.discovery.listing_update import LISTING_UPDATE_JS, paginate_listing_payloads
from scraper.discovery.locate import (
    LOCATE_JS,
    choose_location_suggestion,
    location_is_consistent,
    location_mismatch_message,
    parse_swiggy_header_location,
)
from scraper.discovery.models import ListingPage
from scraper.swiggy.chrome_session import (
    browser_lifecycle,
    close_chrome,
    note_page_closed,
    note_page_created,
    resolve_browser_mode,
)
from scraper.swiggy.scraper import _existing_or_new_page, _open_browser

HARVEST_JS = Path(__file__).with_name("listing_harvest.js").read_text(encoding="utf-8")
LISTING_API_HINTS = (
    "dapi/restaurants/list",
    "mapi/restaurants/list",
    "restaurants/list/v5",
    "dapi/restaurants/list/v5",
    "restaurants/list/update",
    "dineout/restaurants",
    "dineout/listing",
)
LOCATION_SELECT_HINTS = (
    "address-recommend",
    "misc/address",
    "misc/place",
    "location/search",
    "locations/search",
    "webroutes/location",
    "place/autocomplete",
    "drop-location",
    "get-location",
    "city-info",
    "placeid",
    "place_id",
)


def collect_listing_with_location(
    url: str,
    *,
    platform: str,
    query: str,
    category: str,
    browser_mode: str | None = None,
    expected_lat: float | None = None,
    expected_lng: float | None = None,
    city: str = "",
    state: str = "",
    locality: str = "",
    type_text: str = "",
    verify_only: bool = False,
) -> ListingPage:
    from playwright.sync_api import sync_playwright

    mode = resolve_browser_mode(browser_mode or os.getenv("CATALOGFORGE_BROWSER_MODE", "background"))
    handle = None
    created_page = False
    try:
        with sync_playwright() as playwright:
            handle = _open_browser(playwright, mode)
            browser = handle.browser
            if handle.mode in {"chrome-cdp", "chrome", "chrome-background"}:
                context, _existing = _existing_or_new_page(browser, url)
                page = context.new_page()
                created_page = True
                note_page_created()
            else:
                context = browser.new_context(locale="en-IN", viewport={"width": 1366, "height": 768})
                page = context.new_page()
                created_page = True
                note_page_created()
            payloads: list = []
            listing_ctx: dict[str, str | None] = {"lat": None, "lng": None, "page_type": None}
            location_meta: dict[str, str | None] = {
                "location_id": None,
                "city": None,
                "slug": None,
                "lat": None,
                "lng": None,
            }

            def on_request(request) -> None:
                url = request.url or ""
                lowered = url.lower()
                if "restaurants/list/v5" in lowered:
                    query = parse_qs(urlparse(url).query)
                    if listing_ctx["lat"] is None:
                        listing_ctx["lat"] = (query.get("lat") or [None])[0]
                        listing_ctx["lng"] = (query.get("lng") or [None])[0]
                        listing_ctx["page_type"] = (query.get("page_type") or [None])[0]
                _capture_location_params(url, location_meta)

            def on_response(response) -> None:
                response_url = (response.url or "").lower()
                if any(hint in response_url for hint in LOCATION_SELECT_HINTS) and "list/update" not in response_url:
                    try:
                        body = response.json()
                    except Exception:
                        body = None
                    if isinstance(body, (dict, list)):
                        _merge_location_meta(location_meta, body, response.url)
                if not any(hint in response_url for hint in LISTING_API_HINTS):
                    return
                if "list/update" in response_url:
                    return
                try:
                    body = response.json()
                except Exception:
                    return
                if isinstance(body, (dict, list)):
                    payloads.append(body)

            page.on("request", on_request)
            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("load", timeout=20_000)
            except Exception:
                pass
            typed = (type_text or locality or (query.split(",")[0] if query else "")).strip() or query
            args = {
                "platform": platform,
                "query": typed,
                "type": typed,
                "verify": query,
                "category": category,
                "city": city,
                "state": state,
                "locality": locality,
            }
            selected = ""
            attempts = 3
            for attempt in range(attempts):
                _wait_page(page)
                already = _read_displayed_location(page, platform, query)
                if location_is_consistent(query, already):
                    selected = already
                    break
                payloads.clear()
                listing_ctx["lat"] = None
                listing_ctx["lng"] = None
                if platform == "swiggy":
                    selected = _set_swiggy_location(
                        page, typed, city=city, state=state, locality=locality, verify_query=query
                    )
                elif platform in {"zomato", "magicpin"}:
                    selected = _set_header_location(
                        page, platform, typed, city=city, state=state, locality=locality, verify_query=query
                    )
                else:
                    _evaluate_locate(page, {**args, "phase": "location"})
                    _wait_page(page)
                    selected = _read_displayed_location(page, platform, query)
                if location_is_consistent(query, selected):
                    break
            _wait_page(page)
            if not location_is_consistent(query, selected):
                final = page.url or url
                if created_page:
                    try:
                        page.close()
                        note_page_closed()
                    except Exception:
                        pass
                close_chrome(handle)
                handle = None
                return ListingPage(
                    url=final,
                    html="",
                    payload={
                        "location": {
                            "requested": query,
                            "selected": selected,
                            "verified": False,
                            "platform_location_id": location_meta.get("location_id"),
                        },
                        "browser": browser_lifecycle(),
                    },
                    error=location_mismatch_message(query, selected, final),
                    exhausted=True,
                )
            if verify_only:
                final = page.url or url
                displayed = selected
                if created_page:
                    try:
                        page.close()
                        note_page_closed()
                    except Exception:
                        pass
                close_chrome(handle)
                handle = None
                return ListingPage(
                    url=final,
                    html="",
                    payload={
                        "location": {
                            "requested": query,
                            "selected": displayed,
                            "verified": True,
                            "platform_location_id": location_meta.get("location_id"),
                            "platform_city": location_meta.get("city"),
                            "platform_slug": location_meta.get("slug"),
                            "latitude": location_meta.get("lat") or listing_ctx.get("lat"),
                            "longitude": location_meta.get("lng") or listing_ctx.get("lng"),
                        },
                        "browser": browser_lifecycle(),
                    },
                    exhausted=True,
                )
            if _needs_category(url, platform, category):
                _evaluate_locate(page, {**args, "phase": "category"})
                _wait_page(page)
            try:
                page.evaluate("window.scrollTo(0, 400)")
            except Exception:
                pass
            if not payloads:
                _wait_for_listing_xhr(page)
            if (
                platform == "swiggy"
                and expected_lat is not None
                and expected_lng is not None
                and listing_ctx.get("lat")
                and listing_ctx.get("lng")
            ):
                from scraper.discovery.resolver import coords_km

                distance = coords_km(
                    float(expected_lat),
                    float(expected_lng),
                    float(listing_ctx["lat"]),
                    float(listing_ctx["lng"]),
                )
                if distance > 75:
                    final = page.url or url
                    if created_page:
                        try:
                            page.close()
                            note_page_closed()
                        except Exception:
                            pass
                    close_chrome(handle)
                    handle = None
                    return ListingPage(
                        url=final,
                        html="",
                        payload={"location": {"requested": query, "selected": selected, "verified": False}, "browser": browser_lifecycle()},
                        error=location_mismatch_message(query, selected, final)
                        + f" Listing pin is {distance:.0f} km from the resolved coordinates.",
                        exhausted=True,
                    )
            _wait_for_cards(page)
            initial_xhr = len(payloads)
            initial_cards = _card_count(page)
            last = initial_cards
            listing_exhausted = False
            pagination_extra: dict = {}
            if platform == "swiggy" and payloads:
                payloads, pagination_extra = paginate_listing_payloads(
                    payloads,
                    lambda lat, lng, csrf, offset: _fetch_swiggy_listing_update(
                        page, lat, lng, csrf, offset, listing_ctx.get("page_type")
                    ),
                    lat=listing_ctx.get("lat"),
                    lng=listing_ctx.get("lng"),
                )
                listing_exhausted = bool(pagination_extra.get("exhausted"))
            else:
                stale = 0
                last = -1
                for _ in range(40):
                    count = _card_count(page)
                    if count == last:
                        stale += 1
                        if stale >= 4:
                            break
                    else:
                        stale = 0
                        last = count
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(700)
                    except Exception:
                        break
                listing_exhausted = stale >= 4 and (last if last >= 0 else initial_cards) > 0
            html = ""
            try:
                html = page.content() or ""
            except Exception:
                html = ""
            state = None
            try:
                state = page.evaluate(
                    """() => {
                        for (const key of ['__NEXT_DATA__', '__PRELOADED_STATE__', '__INITIAL_STATE__']) {
                            if (window[key]) return window[key];
                        }
                        return null;
                    }"""
                )
            except Exception:
                state = None
            dom_venues = []
            try:
                dom_venues = page.evaluate(HARVEST_JS) or []
            except Exception:
                dom_venues = []
            apis = list(payloads)
            if state is not None:
                apis.append(state)
            final = page.url or url
            if created_page:
                try:
                    page.close()
                    note_page_closed()
                except Exception:
                    pass
            close_chrome(handle)
            handle = None
            return ListingPage(
                url=final,
                html=html,
                payload={
                    "api_payloads": apis,
                    "dom_venues": dom_venues,
                    "location": {
                        "requested": query,
                        "selected": selected,
                        "verified": True,
                        "platform_location_id": location_meta.get("location_id"),
                        "platform_city": location_meta.get("city"),
                        "platform_slug": location_meta.get("slug"),
                        "latitude": location_meta.get("lat") or listing_ctx.get("lat"),
                        "longitude": location_meta.get("lng") or listing_ctx.get("lng"),
                    },
                    "pagination": {
                        "initial_cards": initial_cards,
                        "final_cards": last if last >= 0 else initial_cards,
                        "listing_xhr_after_location": initial_xhr,
                        "listing_xhr_total": len(payloads),
                        "exhausted": listing_exhausted,
                        "mechanism": pagination_extra.get("path") if platform == "swiggy" else "dom-scroll",
                        "method": pagination_extra.get("method") if platform == "swiggy" else None,
                        "batches": pagination_extra.get("batches"),
                        "update_requests": pagination_extra.get("update_requests"),
                        "reason": pagination_extra.get("reason"),
                        "lat": listing_ctx.get("lat"),
                        "lng": listing_ctx.get("lng"),
                    },
                    "browser": browser_lifecycle(),
                },
                exhausted=listing_exhausted,
            )
    except Exception as exc:
        if handle is not None:
            try:
                close_chrome(handle)
            except Exception:
                pass
        return ListingPage(url=url, html="", blocked=False, error=f"{type(exc).__name__}: {exc}", exhausted=True)


def _needs_category(url: str, platform: str, category: str) -> bool:
    lowered = (url or "").lower()
    if platform == "swiggy" and "/restaurants" in lowered and "dineout" not in lowered:
        return False
    if platform == "swiggy" and "/dineout" in lowered:
        return False
    if platform == "zomato" and "/restaurants" in lowered:
        return bool(re.search(r"din(e|ing)", category or "", re.I))
    return bool(category)


def _evaluate_locate(page, payload: dict):
    try:
        return page.evaluate(LOCATE_JS, payload)
    except Exception:
        return None


def _wait_page(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        try:
            page.wait_for_timeout(1200)
        except Exception:
            pass


def _wait_for_cards(page) -> None:
    try:
        page.wait_for_function(
            """() => [...document.querySelectorAll('a[href]')].some((a) => {
              const href = a.href || '';
              return /-rest\\d+/i.test(href) && !/best-restaurants/i.test(href);
            })""",
            timeout=20_000,
        )
    except Exception:
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass


def _wait_for_listing_xhr(page) -> None:
    try:
        page.wait_for_response(lambda response: any(hint in (response.url or "").lower() for hint in LISTING_API_HINTS), timeout=20_000)
    except Exception:
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass


def _fetch_swiggy_listing_update(page, lat, lng, csrf, offset: dict, page_type: str | None):
    try:
        return page.evaluate(
            LISTING_UPDATE_JS,
            {
                "lat": lat,
                "lng": lng,
                "csrf": csrf,
                "nextOffset": offset.get("nextOffset"),
                "widgetOffset": offset.get("widgetOffset") or {},
                "pageType": page_type or "DESKTOP_WEB_LISTING",
            },
        )
    except Exception:
        return None


def _card_count(page) -> int:
    try:
        return int(
            page.evaluate(
                """() => [...document.querySelectorAll('a[href]')].filter((a) => {
                  const href = a.href || '';
                  return /-rest\\d+/i.test(href) && !/best-restaurants/i.test(href);
                }).length"""
            )
            or 0
        )
    except Exception:
        return 0


def _read_displayed_location(page, platform: str = "swiggy", query: str = "") -> str:
    located = _evaluate_locate(page, {"platform": platform, "query": query, "phase": "read"})
    if isinstance(located, dict):
        raw = str(located.get("displayed") or "")
        parsed = parse_swiggy_header_location(raw) or raw.strip()
        if parsed:
            return parsed
    try:
        raw = str(
            page.evaluate(
                """() => {
                    const skip = /^(other|setup your precise location|precise location|select location|cart|sign in|help|offers|search|swiggy corporate|new|\\d+)$/i;
                    const pick = (text) => {
                      const lines = String(text || '').split(/\\n/).map((s) => s.replace(/\\s+/g, ' ').trim()).filter(Boolean);
                      const addr = lines.find((l) => l.includes(',') && !skip.test(l) && l.length < 180);
                      if (addr) return addr;
                      return lines.find((l) => l.length > 2 && l.length < 80 && !skip.test(l)) || '';
                    };
                    const selectors = [
                        "button[aria-label*='location' i]",
                        "[aria-label*='location' i]",
                        "[class*='LocationContent']",
                        "[class*='LocationContainer']",
                        "[class*='LocationBlock']",
                        ".selectedLocation",
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        const got = pick(el ? (el.innerText || el.textContent || '') : '');
                        if (got) return got;
                    }
                    const hit = [...document.querySelectorAll('div,span,p,button,a')].find((node) => {
                      const box = node.getBoundingClientRect();
                      if (!box.width || box.top > 90 || box.left > 480) return false;
                      return Boolean(pick(node.innerText || node.textContent || ''));
                    });
                    return hit ? pick(hit.innerText || hit.textContent || '') : '';
                }"""
            )
            or ""
        )
        return parse_swiggy_header_location(raw) or raw.strip()
    except Exception:
        return ""


def _set_swiggy_location(
    page, query: str, city: str = "", state: str = "", locality: str = "", verify_query: str | None = None
) -> str:
    check = verify_query or query
    displayed = _read_displayed_location(page, "swiggy", check)
    if location_is_consistent(check, displayed):
        return displayed
    _click_swiggy_location_control(page)
    try:
        page.wait_for_selector("input", timeout=8_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    typed = _type_swiggy_location(page, query)
    try:
        key = re.sub(r"[^a-z0-9]+", "", (locality or query).lower())
        if key:
            page.wait_for_function(
                """(key) => [...document.querySelectorAll('div,span,[role=option]')].some((node) => {
                  const text = (node.innerText || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
                  const box = node.getBoundingClientRect();
                  return text.includes(key) && text.length < 80 && box.top > 40 && box.height < 90;
                })""",
                key,
                timeout=8_000,
            )
    except Exception:
        pass
    try:
        page.wait_for_timeout(600)
    except Exception:
        pass
    picked = _click_swiggy_suggestion(page, check, city=city, locality=locality, state=state)
    try:
        for label in ("Confirm location", "Confirm Location", "Use this location"):
            loc = page.get_by_role("button", name=re.compile(label, re.I))
            if loc.count():
                loc.first.click(timeout=3_000)
                break
    except Exception:
        pass
    try:
        key = re.sub(r"[^a-z0-9]+", "", (locality or query).lower())
        if key:
            page.wait_for_function(
                """(key) => {
                  const header = document.body ? document.body.innerText.slice(0, 1200) : '';
                  return header.toLowerCase().replace(/[^a-z0-9]+/g, '').includes(key);
                }""",
                key,
                timeout=8_000,
            )
    except Exception:
        pass
    if not picked:
        located = _evaluate_locate(
            page,
            {
                "platform": "swiggy",
                "query": query,
                "type": query,
                "verify": check,
                "category": "",
                "phase": "location",
                "city": city,
                "state": state,
                "locality": locality,
            },
        )
        if isinstance(located, dict):
            picked = str(located.get("selectedText") or located.get("displayed") or "")
    _wait_page(page)
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass
    displayed = _read_displayed_location(page, "swiggy", check)
    chosen = picked or displayed
    if location_is_consistent(check, chosen):
        return chosen
    if location_is_consistent(check, displayed):
        return displayed
    if typed and location_is_consistent(check, displayed):
        return displayed
    return displayed or chosen


def _click_swiggy_location_control(page) -> bool:
    try:
        clicked = page.evaluate(
            """() => {
              function textOf(el) {
                return el ? String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim() : '';
              }
              function visible(el) {
                if (!el) return false;
                const box = el.getBoundingClientRect();
                return box.width > 0 && box.height > 0 && box.top < 96;
              }
              const nodes = [...document.querySelectorAll('a, button, div, span, p, img')].filter(visible);
              function findNeedle(needles) {
                return nodes.find((node) => {
                  const text = textOf(node).toLowerCase();
                  const alt = String(node.getAttribute && node.getAttribute('alt') || '').toLowerCase();
                  const href = String(node.getAttribute && node.getAttribute('href') || node.href || '').toLowerCase();
                  return needles.some((needle) => text === needle || text.includes(needle) || alt.includes(needle) || href.includes(needle));
                });
              }
              const left = findNeedle(['swiggy']);
              const right = findNeedle(['swiggy corporate']);
              const leftBox = left ? left.getBoundingClientRect() : { right: 8 };
              const rightBox = right ? right.getBoundingClientRect() : { left: 420 };
              const candidates = [...document.querySelectorAll('div, span, button, a, p')].filter((node) => {
                if (!visible(node)) return false;
                const box = node.getBoundingClientRect();
                if (box.height > 80) return false;
                if (box.left < leftBox.right - 4) return false;
                if (box.left >= rightBox.left - 2) return false;
                const text = textOf(node);
                if (!text || text.length > 90) return false;
                if (/^(cart|sign in|help|offers|search|swiggy corporate|new|\\d+)$/i.test(text)) return false;
                if (/search for restaurant|corporate|biryani|kebab|barbecue|north indian/i.test(text)) return false;
                return true;
              });
              const preferred = candidates.find((node) => /,/.test(textOf(node))) || candidates[0];
              if (!preferred) return false;
              preferred.click();
              return true;
            }"""
        )
        if clicked:
            return True
    except Exception:
        pass
    labels = [
        "Setup your precise location",
        "precise location",
        "Select location",
        "Search for area",
    ]
    for label in labels:
        try:
            loc = page.get_by_text(re.compile(label, re.I)).first
            if loc.count():
                loc.click(timeout=4_000)
                return True
        except Exception:
            continue
    for sel in ["[class*='LocationContainer']", "[class*='LocationContent']", "[class*='LocationBlock']"]:
        try:
            page.locator(sel).first.click(timeout=3_000)
            return True
        except Exception:
            continue
    try:
        other = page.get_by_text(re.compile(r"^Other$", re.I)).first
        if other.count():
            other.click(timeout=3_000)
            return True
    except Exception:
        pass
    return False


def _is_venue_search_placeholder(placeholder: str) -> bool:
    return bool(re.search(r"restaurant|cuisine|dish|places,\s*cuisines|search for food", placeholder or "", re.I))


def _type_into_location_field(field, query: str) -> bool:
    field.click(timeout=3_000)
    try:
        field.fill("")
    except Exception:
        pass
    try:
        field.press_sequentially(query, delay=50)
        return True
    except Exception:
        pass
    try:
        field.type(query, delay=50)
        return True
    except Exception:
        field.fill(query)
        return True


def _type_swiggy_location(page, query: str) -> bool:
    selectors = [
        "input[placeholder*='area, street' i]",
        "input[placeholder*='street name' i]",
        "input[placeholder*='location' i]",
        "input[placeholder*='Search for area' i]",
        "input[aria-label*='location' i]",
        "input[type='text']",
    ]
    for sel in selectors:
        try:
            field = page.locator(sel).first
            if not field.count():
                continue
            placeholder = ""
            try:
                placeholder = str(field.get_attribute("placeholder") or "") + " " + str(field.get_attribute("aria-label") or "")
            except Exception:
                placeholder = ""
            if _is_venue_search_placeholder(placeholder):
                continue
            return _type_into_location_field(field, query)
        except Exception:
            continue
    return False


def _click_swiggy_suggestion(page, query: str, city: str = "", locality: str = "", state: str = "") -> str:
    skip = re.compile(
        r"cart|sign in|help|offers|search|swiggy corporate|company|about us|careers|"
        r"top restaurant|online food delivery|best restaurants",
        re.I,
    )
    candidates: list[str] = []
    locators = page.locator("[role='option'], [role='listbox'] [role='option']")
    try:
        count = min(locators.count(), 16)
    except Exception:
        count = 0
    for index in range(count):
        try:
            text = re.sub(r"\s+", " ", locators.nth(index).inner_text(timeout=1_000)).strip()
        except Exception:
            continue
        if text and not skip.search(text) and text not in candidates:
            candidates.append(text)
    if not candidates:
        try:
            extra = page.evaluate(
                """() => {
                  const rows = [...document.querySelectorAll('div,span,[role=option]')].map((node) => {
                    const box = node.getBoundingClientRect();
                    const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (!text || text.length < 8 || text.length > 120) return null;
                    if (!box.width || box.height > 90 || box.top < 48) return null;
                    if (node.querySelector('input')) return null;
                    return {text, top: box.top, height: box.height};
                  }).filter(Boolean);
                  rows.sort((a, b) => a.top - b.top || a.height - b.height);
                  const seen = [];
                  for (const row of rows) {
                    if (!seen.includes(row.text)) seen.push(row.text);
                  }
                  return seen;
                }"""
            )
        except Exception:
            extra = []
        for text in extra or []:
            if isinstance(text, str) and text not in candidates and not skip.search(text):
                candidates.append(text)
    best_text = choose_location_suggestion(
        candidates, query, locality=locality, city=city, state=state
    )
    if not best_text:
        return ""
    try:
        clicked = page.evaluate(
            """(wanted) => {
              const hits = [...document.querySelectorAll('div,span,[role=option]')].filter((node) => {
                const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                return text === wanted;
              });
              if (!hits.length) return false;
              hits.sort((a, b) => a.getBoundingClientRect().height - b.getBoundingClientRect().height);
              hits[0].click();
              return true;
            }""",
            best_text,
        )
        if clicked:
            return best_text
    except Exception:
        pass
    try:
        page.get_by_text(best_text, exact=True).first.click(timeout=5_000)
        return best_text
    except Exception:
        return ""


def _set_header_location(
    page, platform: str, query: str, city: str = "", state: str = "", locality: str = "", verify_query: str | None = None
) -> str:
    check = verify_query or query
    displayed = _read_displayed_location(page, platform, check)
    if location_is_consistent(check, displayed):
        return displayed
    _click_header_location_control(page, platform)
    try:
        page.wait_for_selector("input", timeout=8_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    _type_header_location(page, platform, query)
    try:
        page.wait_for_selector("[role='option'], [role='listbox']", timeout=8_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass
    picked = _click_swiggy_suggestion(page, check, city=city, locality=locality, state=state)
    if not picked:
        located = _evaluate_locate(
            page,
            {
                "platform": platform,
                "query": query,
                "type": query,
                "verify": check,
                "category": "",
                "phase": "location",
                "city": city,
                "state": state,
                "locality": locality,
            },
        )
        if isinstance(located, dict):
            picked = str(located.get("selectedText") or located.get("displayed") or "")
    _wait_page(page)
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass
    displayed = _read_displayed_location(page, platform, check)
    if location_is_consistent(check, displayed):
        return displayed
    if location_is_consistent(check, picked):
        return picked
    return displayed or picked


def _click_header_location_control(page, platform: str) -> bool:
    if platform == "magicpin":
        for sel in [".selectedLocation", "[class*='selectedLocation']", "input.location"]:
            try:
                page.locator(sel).first.click(timeout=3_000)
                return True
            except Exception:
                continue
    if platform == "zomato":
        for sel in [
            "button[aria-label*='location' i]",
            "[aria-label*='location' i]",
            "[class*='locationDropDown']",
            "[class*='header-location']",
        ]:
            try:
                page.locator(sel).first.click(timeout=3_000)
                return True
            except Exception:
                continue
    try:
        clicked = page.evaluate(
            """(platform) => {
              function textOf(el) {
                return el ? String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim() : '';
              }
              function visible(el) {
                if (!el) return false;
                const box = el.getBoundingClientRect();
                return box.width > 0 && box.height > 0 && box.top < 96;
              }
              const nodes = [...document.querySelectorAll('a, button, div, span, p, img')].filter(visible);
              function findNeedle(needles) {
                return nodes.find((node) => {
                  const text = textOf(node).toLowerCase();
                  const alt = String(node.getAttribute && node.getAttribute('alt') || '').toLowerCase();
                  const href = String(node.getAttribute && node.getAttribute('href') || node.href || '').toLowerCase();
                  return needles.some((needle) => text === needle || text.includes(needle) || alt.includes(needle) || href.includes(needle));
                });
              }
              const leftNeedles = platform === 'zomato' ? ['zomato'] : ['magicpin'];
              const rightNeedles = platform === 'zomato'
                ? ['search for restaurant', 'search for cuisine']
                : ['search for places', 'cuisines, and more'];
              const left = findNeedle(leftNeedles);
              const right = findNeedle(rightNeedles);
              const leftBox = left ? left.getBoundingClientRect() : { right: 8 };
              const rightBox = right ? right.getBoundingClientRect() : { left: 520 };
              const skip = /^(cart|sign in|log in|help|offers|search|swiggy corporate|zomato|magicpin|new|\\d+)$/i;
              const candidates = [...document.querySelectorAll('div,span,button,a,p')].filter((node) => {
                if (!visible(node)) return false;
                const box = node.getBoundingClientRect();
                if (box.height > 80) return false;
                if (box.left < leftBox.right - 4) return false;
                if (box.left >= rightBox.left - 2) return false;
                const text = textOf(node);
                if (!text || text.length > 80 || skip.test(text)) return false;
                if (/search for restaurant|search for places, cuisines/i.test(text)) return false;
                return true;
              });
              const preferred = candidates.find((node) => /,/.test(textOf(node))) || candidates[0];
              if (!preferred) return false;
              preferred.click();
              return true;
            }""",
            platform,
        )
        if clicked:
            return True
    except Exception:
        pass
    return False


def _type_header_location(page, platform: str, query: str) -> bool:
    selectors = [
        "input.location",
        "input[placeholder*='Search Location' i]",
        "input[placeholder*='delivery location' i]",
        "input[aria-label*='location' i]",
        "input[placeholder*='location' i]",
        "input[placeholder*='Detect' i]",
        "input[type='text']",
    ]
    if platform == "swiggy":
        return _type_swiggy_location(page, query)
    for sel in selectors:
        try:
            field = page.locator(sel).first
            if not field.count():
                continue
            placeholder = ""
            try:
                placeholder = str(field.get_attribute("placeholder") or "") + " " + str(field.get_attribute("aria-label") or "")
            except Exception:
                placeholder = ""
            if _is_venue_search_placeholder(placeholder):
                continue
            return _type_into_location_field(field, query)
        except Exception:
            continue
    return False


def _capture_location_params(url: str, location_meta: dict[str, str | None]) -> None:
    query = parse_qs(urlparse(url or "").query)
    for key, dest in (
        ("place_id", "location_id"),
        ("placeId", "location_id"),
        ("locationId", "location_id"),
        ("city_id", "location_id"),
        ("cityId", "location_id"),
        ("entity_id", "location_id"),
        ("lat", "lat"),
        ("lng", "lng"),
        ("lon", "lng"),
        ("city", "city"),
    ):
        value = (query.get(key) or [None])[0]
        if value and not location_meta.get(dest):
            location_meta[dest] = value


def _merge_location_meta(location_meta: dict[str, str | None], body: object, url: str = "") -> None:
    _capture_location_params(url, location_meta)
    stack = [body]
    keys = {
        "place_id": "location_id",
        "placeId": "location_id",
        "locationId": "location_id",
        "city_id": "location_id",
        "cityId": "location_id",
        "entity_id": "location_id",
        "entityId": "location_id",
        "lat": "lat",
        "latitude": "lat",
        "lng": "lng",
        "lon": "lng",
        "longitude": "lng",
        "cityName": "city",
        "city_name": "city",
    }
    seen = 0
    while stack and seen < 80:
        node = stack.pop()
        seen += 1
        if isinstance(node, dict):
            for key, dest in keys.items():
                value = node.get(key)
                if value not in (None, "") and not location_meta.get(dest):
                    location_meta[dest] = str(value)
            stack.extend(list(node.values())[:12])
        elif isinstance(node, list):
            stack.extend(node[:8])
