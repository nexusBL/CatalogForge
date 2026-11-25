"""Server-side item/category resolution. Model IDs are ignored."""

from __future__ import annotations

from dataclasses import dataclass

from backend.canonical.adapter import to_canonical_from_response
from backend.review_intel.contract import CatalogueItemRef
from backend.review_intel.link import catalogue_item_refs, link_review_text, normalize_item_name
from backend.schemas import CatalogCreateResponse


@dataclass(frozen=True)
class ResolvedItem:
    item_id: str
    name: str
    path: str
    category_name: str
    item: dict
    category_index: int
    item_index: int


@dataclass(frozen=True)
class Resolution:
    status: str
    item: ResolvedItem | None = None
    category_name: str | None = None
    category_index: int | None = None
    candidates: tuple[str, ...] = ()


def category_entries(result: CatalogCreateResponse) -> list[tuple[int, str, list[dict]]]:
    rows: list[tuple[int, str, list[dict]]] = []
    for index, category in enumerate(result.categories or []):
        if not isinstance(category, dict):
            continue
        name = str(category.get("name") or "").strip()
        raw_items = category.get("items") if isinstance(category.get("items"), list) else []
        items = [item for item in raw_items if isinstance(item, dict)]
        rows.append((index, name, items))
    return rows


def resolve_category(result: CatalogCreateResponse, name: str | None) -> Resolution:
    rows = category_entries(result)
    if not name or not name.strip():
        if len(rows) == 1:
            index, category_name, _items = rows[0]
            return Resolution(status="exact", category_name=category_name, category_index=index)
        return Resolution(status="missing_category")
    needle = normalize_item_name(name)
    exact: list[tuple[int, str]] = []
    normalized: list[tuple[int, str]] = []
    for index, category_name, _items in rows:
        if category_name == name.strip():
            exact.append((index, category_name))
        elif normalize_item_name(category_name) == needle:
            normalized.append((index, category_name))
    hits = exact or normalized
    if not hits:
        return Resolution(status="missing_category", category_name=name.strip())
    if len(hits) > 1:
        return Resolution(status="ambiguous_category", candidates=tuple(row[1] for row in hits))
    index, category_name = hits[0]
    return Resolution(status="exact" if exact else "normalized", category_name=category_name, category_index=index)


def resolve_item_id(result: CatalogCreateResponse, item_id: str | None) -> Resolution:
    token = (item_id or "").strip()
    if not token:
        return Resolution(status="missing_item")
    for category_index, category_name, items in category_entries(result):
        for item_index, item in enumerate(items):
            current_id = str(item.get("item_id") or item.get("id") or "").strip()
            extra = item.get("additional_information") if isinstance(item.get("additional_information"), dict) else {}
            source_id = str(extra.get("id") or "").strip()
            if token not in {current_id, source_id}:
                continue
            resolved_id = current_id or source_id or token
            return Resolution(
                status="exact",
                item=ResolvedItem(
                    item_id=resolved_id,
                    name=str(item.get("name") or ""),
                    path=f"menus[0].categories[{category_index}].items[{item_index}]",
                    category_name=category_name,
                    item=item,
                    category_index=category_index,
                    item_index=item_index,
                ),
                category_name=category_name,
            )
    return Resolution(status="missing_item")


def resolve_item_name(
    result: CatalogCreateResponse,
    item_name: str | None,
    *,
    category_name: str | None = None,
) -> Resolution:
    if not item_name or not item_name.strip():
        return Resolution(status="missing_item")
    refs = catalogue_item_refs(to_canonical_from_response(result))
    if category_name:
        wanted = normalize_item_name(category_name)
        refs = [ref for ref in refs if normalize_item_name(ref.category_name or "") == wanted]
        if not refs:
            return Resolution(status="missing_item", category_name=category_name)
    hits = link_review_text(item_name.strip(), refs)
    useful = [row for row in hits if row.status in {"exact", "normalized", "ambiguous"}]
    if not useful:
        return Resolution(status="missing_item")
    if any(row.status == "ambiguous" for row in useful) or _many_ids(useful):
        return Resolution(status="ambiguous_item", candidates=_candidate_labels(refs, useful))
    match = next(row for row in useful if row.status in {"exact", "normalized"})
    located = _locate(result, match.item_id, match.path, match.item_name)
    if located is None:
        return Resolution(status="missing_item")
    return Resolution(status=match.status, item=located, category_name=located.category_name)


def _many_ids(rows: list) -> bool:
    ids = {row.item_id for row in rows if row.status in {"exact", "normalized"} and row.item_id}
    return len(ids) > 1


def _candidate_labels(refs: list[CatalogueItemRef], rows: list) -> tuple[str, ...]:
    wanted: set[str] = set()
    for row in rows:
        if row.item_id:
            wanted.add(row.item_id)
        wanted.update(getattr(row, "candidate_item_ids", None) or [])
    labels: list[str] = []
    for ref in refs:
        token = ref.item_id or ref.path
        if token in wanted:
            labels.append(f"{ref.name} ({ref.category_name or 'menu'})")
    return tuple(dict.fromkeys(labels))


def _locate(result: CatalogCreateResponse, item_id: str | None, path: str | None, name: str | None) -> ResolvedItem | None:
    for category_index, category_name, items in category_entries(result):
        for item_index, item in enumerate(items):
            current_id = str(item.get("item_id") or item.get("id") or "").strip()
            if item_id and current_id == item_id:
                return ResolvedItem(
                    item_id=current_id,
                    name=str(item.get("name") or name or ""),
                    path=path or f"menus[0].categories[{category_index}].items[{item_index}]",
                    category_name=category_name,
                    item=item,
                    category_index=category_index,
                    item_index=item_index,
                )
    if not name:
        return None
    needle = normalize_item_name(name)
    hits: list[ResolvedItem] = []
    for category_index, category_name, items in category_entries(result):
        for item_index, item in enumerate(items):
            if normalize_item_name(str(item.get("name") or "")) != needle:
                continue
            current_id = str(item.get("item_id") or item.get("id") or "")
            hits.append(
                ResolvedItem(
                    item_id=current_id,
                    name=str(item.get("name") or name),
                    path=path or f"menus[0].categories[{category_index}].items[{item_index}]",
                    category_name=category_name,
                    item=item,
                    category_index=category_index,
                    item_index=item_index,
                )
            )
    if len(hits) == 1:
        return hits[0]
    return None
