"""Interactive venue-gallery traversal for Zomato and Magicpin (Chrome/CDP).

Swiggy Dineout still uses scraper.swiggy.scraper._open_dineout_image_gallery.
"""

from __future__ import annotations

import re
from typing import Any

PHOTO_PLUS_RE = re.compile(r"\+\s*\d+\s*Photos?", re.I)
OWNED_REJECT_RE = re.compile(
    r"similar restaurant|nearby restaurant|more restaurants|recommended|sponsored|brands near|near this",
    re.I,
)
GALLERY_TRIGGER_RE = re.compile(
    r"view gallery|view all photos|show all images|view all images|\+\s*\d+\s*photos?",
    re.I,
)

HARVEST_JS = """() => {
  const reject = /similar restaurant|nearby restaurant|more restaurants|recommended|sponsored|brands near|near this/i;
  const junk = /icon|logo|sprite|placeholder|web_assets|favicon|veg-icon|non-veg/i;
  const roots = [...document.querySelectorAll('[role="dialog"], [aria-modal="true"], .lightbox, .gallery, [class*="Gallery"], [class*="lightbox"]')]
    .filter((el) => el && el.getClientRects && el.getClientRects().length);
  const scope = roots[0] || document;
  const items = [];
  const seen = new Set();
  for (const img of scope.querySelectorAll("img")) {
    const src = img.currentSrc || img.src || "";
    const alt = img.alt || "";
    const ctx = ((img.closest("a,figure,li,div") || img).innerText || "");
    if (!/^https?:/i.test(src) || junk.test(src) || reject.test(alt) || reject.test(ctx)) continue;
    const key = (src.split("?")[0] || "").toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    items.push({ url: src, alt, category: "gallery" });
  }
  return items;
}"""


def should_traverse_gallery(url: str | None) -> bool:
    text = (url or "").lower()
    if "/order" in text or "/delivery" in text:
        return False
    if "swiggy.com" in text:
        return False
    if "zomato.com" in text or "magicpin.in" in text:
        return True
    return False


def photo_plus_label(text: str | None) -> bool:
    return bool(PHOTO_PLUS_RE.search(text or ""))


def is_owned_gallery_context(alt: str | None, nearby_text: str | None) -> bool:
    blob = f"{alt or ''} {nearby_text or ''}"
    return not bool(OWNED_REJECT_RE.search(blob))


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


def _open_gallery_controls(page) -> bool:
    opened = _click_visible(page.get_by_text(re.compile(r"View Gallery", re.I)))
    if not opened:
        opened = _click_visible(page.get_by_text(PHOTO_PLUS_RE))
    if not opened:
        opened = _click_visible(page.get_by_text(re.compile(r"View all photos|Show all images|View all images", re.I)))
    if not opened:
        opened = _click_visible(page.get_by_role("button", name=re.compile(r"photos|gallery", re.I)))
    return opened


def _click_next(page) -> bool:
    if _click_visible(page.get_by_role("button", name=re.compile(r"next|next image|next slide|right", re.I))):
        return True
    if _click_visible(page.locator('[aria-label*="Next" i], [aria-label*="next image" i], [aria-label*="right" i]')):
        return True
    if _click_visible(page.locator('button:has-text("›"), button:has-text(">"), [class*="arrow" i][class*="right" i], [class*="rightArrow" i], [class*="swiper-button-next" i]')):
        return True
    if _click_visible(page.locator('[role="dialog"] button:has(svg), [aria-modal="true"] button:has(svg), .lightbox button:has(svg), [class*="modal" i] button:has(svg)')):
        return True
    try:
        page.keyboard.press("ArrowRight")
        return True
    except Exception:
        return False


def open_interactive_gallery(page) -> list[dict[str, Any]]:
    photos: list[dict[str, Any]] = []
    seen: set[str] = set()

    def harvest() -> None:
        try:
            items = page.evaluate(HARVEST_JS) or []
        except Exception:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str):
                continue
            if not is_owned_gallery_context(item.get("alt"), None):
                continue
            key = url.split("?")[0].lower()
            if not key or key in seen:
                continue
            seen.add(key)
            photos.append({"url": url, "category": item.get("category") or "gallery"})

    harvest()
    _open_gallery_controls(page)
    try:
        page.wait_for_timeout(1_200)
    except Exception:
        pass
    harvest()
    stale = 0
    for _ in range(400):
        before = len(photos)
        if not _click_next(page):
            break
        try:
            page.wait_for_timeout(900)
        except Exception:
            pass
        harvest()
        if len(photos) == before:
            stale += 1
            if stale >= 2:
                break
        else:
            stale = 0
    harvest()
    return photos
