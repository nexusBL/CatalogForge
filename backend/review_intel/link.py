"""Deterministic catalogue-item linkage. No fuzzy or semantic matching."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.grading.document import iter_menu_items
from backend.review_intel.contract import CatalogueItemRef, ReviewLinkage


def normalize_item_name(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def catalogue_item_refs(document: CanonicalDocument) -> list[CatalogueItemRef]:
    refs: list[CatalogueItemRef] = []
    for path, category, item in iter_menu_items(document):
        name = (item.name or "").strip()
        if not name:
            continue
        item_id = (item.item_id or "").strip() or None
        refs.append(
            CatalogueItemRef(
                item_id=item_id,
                name=name,
                path=path,
                category_name=(category.name or "").strip() or None,
            )
        )
    return refs


def link_review_text(text: str, items: list[CatalogueItemRef]) -> list[ReviewLinkage]:
    """Return zero or more linkages. Never silently picks among ambiguous items."""
    body = text or ""
    if not body.strip() or not items:
        return [ReviewLinkage(status="no_match")]

    by_exact: dict[str, list[CatalogueItemRef]] = {}
    by_norm: dict[str, list[CatalogueItemRef]] = {}
    for item in items:
        by_exact.setdefault(item.name, []).append(item)
        norm = normalize_item_name(item.name)
        if norm:
            by_norm.setdefault(norm, []).append(item)

    exact_hits = _hits_for(body, by_exact, casefold=False)
    if exact_hits:
        return exact_hits

    normalized_body = normalize_item_name(body)
    norm_hits = _hits_for(normalized_body, by_norm, casefold=True, original_text=body)
    if norm_hits:
        return norm_hits
    return [ReviewLinkage(status="no_match")]


def _hits_for(
    haystack: str,
    grouped: dict[str, list[CatalogueItemRef]],
    *,
    casefold: bool,
    original_text: str | None = None,
) -> list[ReviewLinkage]:
    names = sorted(grouped, key=len, reverse=True)
    kept: list[tuple[str, int, int]] = []
    search = haystack
    for name in names:
        if not name:
            continue
        start = 0
        while True:
            idx = search.find(name, start)
            if idx < 0:
                break
            end = idx + len(name)
            if _contained_in_longer(idx, end, kept):
                start = end
                continue
            kept.append((name, idx, end))
            start = end
    if not kept:
        return []
    linkages: list[ReviewLinkage] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for name, _start, _end in kept:
        candidates = grouped[name]
        ids = tuple(sorted({item.item_id or item.path for item in candidates}))
        key = (name, ids)
        if key in seen:
            continue
        seen.add(key)
        span_source = original_text if casefold else haystack
        span = name if not casefold else _span_from_original(span_source or haystack, candidates[0].name)
        unique_ids = {item.item_id for item in candidates if item.item_id}
        if len(candidates) > 1 and (len(unique_ids) != 1):
            linkages.append(
                ReviewLinkage(
                    status="ambiguous",
                    span_text=span,
                    candidate_item_ids=[item.item_id or item.path for item in candidates],
                )
            )
            continue
        chosen = candidates[0]
        linkages.append(
            ReviewLinkage(
                status="normalized" if casefold else "exact",
                item_id=chosen.item_id,
                item_name=chosen.name,
                path=chosen.path,
                span_text=span,
                candidate_item_ids=[chosen.item_id or chosen.path],
            )
        )
    return linkages


def _contained_in_longer(start: int, end: int, kept: list[tuple[str, int, int]]) -> bool:
    for _name, left, right in kept:
        if start >= left and end <= right:
            return True
    return False


def _span_from_original(text: str, name: str) -> str:
    lowered = text.casefold()
    needle = name.casefold()
    idx = lowered.find(needle)
    if idx < 0:
        return name
    return text[idx : idx + len(name)]
