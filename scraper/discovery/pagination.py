from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

NEXT_REL_RE = re.compile(r"""<a\b[^>]+rel=["']next["'][^>]*href=["']([^"']+)["']""", re.I)
HREF_NEXT_RE = re.compile(r"""<a\b[^>]+href=["']([^"']+)["'][^>]*>\s*(?:next|load more)\s*<""", re.I)
LOAD_MORE_RE = re.compile(
    r"""<(?:a|button)\b[^>]*(?:data-next(?:-page|-url)?|data-load-more)=["']([^"']+)["']""",
    re.I,
)
PAGE_PARAM_RE = re.compile(r"""<a\b[^>]+href=["']([^"']*[?&]page=(\d+)[^"']*)["']""", re.I)
HAS_MORE_RE = re.compile(r'data-has-more=["\'](?:true|1)["\']', re.I)
NO_MORE_RE = re.compile(r'data-has-more=["\'](?:false|0)["\']', re.I)
INFINITE_PAGE_RE = re.compile(r'data-discovery-page=["\'](\d+)["\']', re.I)


def next_page_url(html: str, current_url: str) -> str | None:
    scoped = html or ""
    for pattern in (NEXT_REL_RE, LOAD_MORE_RE, HREF_NEXT_RE):
        match = pattern.search(scoped)
        if match:
            return urljoin(current_url, match.group(1))
    current = urlparse(current_url)
    current_page = _page_number(current_url) or 1
    best: tuple[int, str] | None = None
    for href, page_text in PAGE_PARAM_RE.findall(scoped):
        page = int(page_text)
        if page > current_page and (best is None or page < best[0]):
            best = (page, urljoin(current_url, href))
    if best:
        return best[1]
    if HAS_MORE_RE.search(scoped) and not NO_MORE_RE.search(scoped):
        return _with_page(current_url, current_page + 1)
    return None


def listing_exhausted(html: str, next_url: str | None) -> bool:
    if NO_MORE_RE.search(html or ""):
        return True
    return not next_url


def infinite_scroll_page_count(html: str) -> int:
    pages = [int(value) for value in INFINITE_PAGE_RE.findall(html or "")]
    return max(pages) if pages else (1 if (html or "").strip() else 0)


def _page_number(url: str) -> int | None:
    values = parse_qs(urlparse(url).query).get("page") or []
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def _with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["page"] = [str(page)]
    encoded = urlencode({key: values[0] for key, values in query.items()})
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, encoded, parsed.fragment))
