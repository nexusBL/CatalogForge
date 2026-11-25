from __future__ import annotations

from typing import Any, Callable

LISTING_UPDATE_PATH = "/dapi/restaurants/list/update"

FetchUpdate = Callable[[str | None, str | None, str | None, dict[str, Any]], Any]


def listing_data(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and ("pageOffset" in data or "cards" in data or "nextFetch" in data):
        return data
    if "pageOffset" in payload:
        return payload
    return None


def offset_from_listing(payload: Any) -> dict[str, Any] | None:
    data = listing_data(payload)
    offset = data.get("pageOffset") if data else None
    return offset if isinstance(offset, dict) else None


def next_offset_token(payload: Any) -> str:
    offset = offset_from_listing(payload) or {}
    token = offset.get("nextOffset")
    if token in (None, ""):
        return ""
    return str(token).strip()


def listing_has_more(payload: Any) -> bool:
    """Swiggy's listing.js only calls updateListing when pageOffset.nextOffset is truthy."""
    return bool(next_offset_token(payload))


def last_listing_payload(payloads: list[Any]) -> Any | None:
    for item in reversed(payloads):
        if listing_data(item) is not None:
            return item
    return None


def paginate_listing_payloads(
    payloads: list[Any],
    fetch_update: FetchUpdate,
    *,
    lat: str | None,
    lng: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Replay Swiggy LISTING_UPDATE until nextOffset is missing or the offset pair does not advance."""
    collected = list(payloads)
    seen: set[tuple[str, str]] = set()
    update_count = 0
    reason = ""
    exhausted = False
    while True:
        current = last_listing_payload(collected)
        token = next_offset_token(current)
        if not token:
            exhausted = True
            reason = "missing nextOffset"
            break
        offset = offset_from_listing(current) or {}
        widget = offset.get("widgetOffset") if isinstance(offset.get("widgetOffset"), dict) else {}
        progress = (token, str(sorted(widget.items())))
        if progress in seen:
            exhausted = True
            reason = "unchanged nextOffset and widgetOffset"
            break
        seen.add(progress)
        csrf = current.get("csrfToken") if isinstance(current, dict) else None
        nxt = fetch_update(lat, lng, csrf, offset)
        if not isinstance(nxt, dict):
            exhausted = True
            reason = "update request failed"
            break
        if nxt.get("statusCode") not in (0, None, "0"):
            exhausted = True
            reason = f"update statusCode {nxt.get('statusCode')}"
            collected.append(nxt)
            update_count += 1
            break
        collected.append(nxt)
        update_count += 1
    return collected, {
        "exhausted": exhausted,
        "reason": reason,
        "update_requests": update_count,
        "batches": (1 if last_listing_payload(payloads) is not None else 0) + update_count,
        "path": LISTING_UPDATE_PATH,
        "method": "POST",
    }


LISTING_UPDATE_JS = """
async ({ lat, lng, csrf, nextOffset, widgetOffset, pageType }) => {
  const res = await fetch("/dapi/restaurants/list/update", {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      lat,
      lng,
      nextOffset,
      widgetOffset,
      filters: {},
      seoParams: {
        seoUrl: "https://www.swiggy.com/restaurants",
        pageType: "FOOD_HOMEPAGE",
        apiContext: "foodhome",
      },
      page_type: pageType || "DESKTOP_WEB_LISTING",
      _csrf: csrf,
    }),
  });
  return await res.json();
}
"""
