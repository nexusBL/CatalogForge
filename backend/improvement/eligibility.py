"""Resolve Phase 5 findings into V1 improvement targets without mutating the catalogue."""

from __future__ import annotations

import re
from collections import Counter

from backend.canonical.models import CanonicalDocument, CanonicalMenuCategory, CanonicalMenuItem
from backend.grade_explain.contract import Finding, GradeExplanation
from backend.grading.document import iter_menu_items
from backend.catalogue_normalize import coerce_price
from backend.improvement.contract import (
    CATALOGUE_STATE_DRIVERS,
    CATEGORY_NAME_CHECK_IDS,
    DESCRIPTION_CHECK_IDS,
    ITEM_PRICE_CHECK_IDS,
    MAX_LINES_PER_REQUEST,
    MEDIA_HANDOFF_CHECK_IDS,
    UNSAFE_MENU_MOVE_CHECK_IDS,
    UNSUPPORTED_INVENT_CHECK_IDS,
    V1_SUPPORTED_DRIVERS,
    ResolvedImprovement,
    TrustedItemContext,
)
from backend.improvement.kinds import DRIVER_KIND, KIND_REGISTRY

ITEM_PATH_RE = re.compile(
    r"^menus\[(\d+)\]\.categories\[(\d+)\]\.items\[(\d+)\](?:\.(description|labels|image_url|price|name))?$"
)
CATEGORY_PATH_RE = re.compile(r"^menus\[(\d+)\]\.categories\[(\d+)\](?:\.name)?$")
VENUE_IMAGE_RE = re.compile(r"^(?:venue|restaurant)\.image_url$")
CATALOGUE_IMAGES_RE = re.compile(r"^catalogue\.images$")


class ImprovementUnsupported(ValueError):
    """Finding cannot produce a V1 proposal."""


class TooManyImprovementPaths(ValueError):
    """Client requested more than the V1 line cap."""


def _item_at(document: CanonicalDocument, menu_i: int, cat_i: int, item_i: int) -> tuple[CanonicalMenuCategory, CanonicalMenuItem, str] | None:
    if menu_i >= len(document.menus):
        return None
    menu = document.menus[menu_i]
    if cat_i >= len(menu.categories):
        return None
    category = menu.categories[cat_i]
    if item_i >= len(category.items):
        return None
    path = f"menus[{menu_i}].categories[{cat_i}].items[{item_i}]"
    return category, category.items[item_i], path


def _category_at(document: CanonicalDocument, menu_i: int, cat_i: int) -> tuple[CanonicalMenuCategory, str] | None:
    if menu_i >= len(document.menus):
        return None
    menu = document.menus[menu_i]
    if cat_i >= len(menu.categories):
        return None
    path = f"menus[{menu_i}].categories[{cat_i}]"
    return menu.categories[cat_i], path


def _description_blank(value: str | None) -> bool:
    return value is None or not str(value).strip()


def _item_context(
    *,
    document: CanonicalDocument,
    category: CanonicalMenuCategory,
    item: CanonicalMenuItem,
    item_path: str,
    kind: ImprovementKind,
    current_value: str | None,
    field: str | None = None,
) -> TrustedItemContext:
    suffix = field or ("description" if kind == "description" else "name")
    if kind == "labels":
        suffix = "labels"
    elif kind == "media_handoff":
        suffix = "image_url"
    elif kind == "item_price":
        suffix = "price"
    original = coerce_price(item.original_price if item.original_price is not None else item.price)
    food = (item.food_type or "").strip()
    labels = [str(label).strip() for label in item.labels if str(label).strip()]
    needs_ollama = True
    if kind in {"media_handoff", "item_price"}:
        needs_ollama = False
    return TrustedItemContext(
        path=f"{item_path}.{suffix}",
        kind=kind,
        item_id=item.item_id or item.source_item_id,
        name=item.name,
        category_name=category.name,
        food_type=item.food_type,
        labels=labels,
        current_value=current_value,
        restaurant_name=document.restaurant_name or (document.venue.name if document.venue else None),
        needs_ollama=needs_ollama,
        original_price=None if original is None else str(original),
        image_url=item.image_url or item.source_image_url,
        media_type="image" if kind == "media_handoff" else None,
    )


def _category_context(
    *,
    document: CanonicalDocument,
    category: CanonicalMenuCategory,
    category_path: str,
) -> TrustedItemContext:
    sample = category.items[0].name if category.items else ""
    return TrustedItemContext(
        path=f"{category_path}.name",
        kind="category_name",
        item_id=None,
        name=sample,
        category_name=category.name,
        food_type=None,
        labels=[],
        current_value=category.name or None,
        restaurant_name=document.restaurant_name or (document.venue.name if document.venue else None),
        needs_ollama=True,
    )


def _missing_description_targets(document: CanonicalDocument) -> list[TrustedItemContext]:
    targets: list[TrustedItemContext] = []
    for item_path, category, item in iter_menu_items(document):
        if _description_blank(item.description):
            targets.append(
                _item_context(
                    document=document,
                    category=category,
                    item=item,
                    item_path=item_path,
                    kind="description",
                    current_value=item.description,
                )
            )
    return targets


def _repeated_description_targets(document: CanonicalDocument) -> list[TrustedItemContext]:
    counts: Counter[str] = Counter()
    rows: list[tuple[str, CanonicalMenuCategory, CanonicalMenuItem]] = []
    for item_path, category, item in iter_menu_items(document):
        text = (item.description or "").strip().casefold()
        if not text:
            continue
        counts[text] += 1
        rows.append((item_path, category, item))
    targets: list[TrustedItemContext] = []
    for item_path, category, item in rows:
        text = (item.description or "").strip().casefold()
        if counts[text] > 1:
            targets.append(
                _item_context(
                    document=document,
                    category=category,
                    item=item,
                    item_path=item_path,
                    kind="description",
                    current_value=item.description,
                )
            )
    return targets


def _empty_label_targets(document: CanonicalDocument) -> list[TrustedItemContext]:
    targets: list[TrustedItemContext] = []
    for item_path, category, item in iter_menu_items(document):
        labels = [str(label).strip() for label in item.labels if str(label).strip()]
        if labels:
            continue
        targets.append(
            _item_context(
                document=document,
                category=category,
                item=item,
                item_path=item_path,
                kind="labels",
                current_value=", ".join(labels) or None,
                field="labels",
            )
        )
    return targets


def _price_target(document: CanonicalDocument, item_path: str, item, category, *, strict: bool) -> TrustedItemContext | None:
    selling = coerce_price(item.price)
    original = coerce_price(item.original_price)
    if original is None:
        if strict:
            raise ImprovementUnsupported(
                "Cannot invent a selling price; original_price is not a trusted numeric value on this item."
            )
        return None
    if selling is not None and selling == original:
        if strict:
            raise ImprovementUnsupported(f"Invalid or ineligible item/path: {item_path}.price")
        return None
    return _item_context(
        document=document,
        category=category,
        item=item,
        item_path=item_path,
        kind="item_price",
        current_value=None if item.price is None else str(item.price),
        field="price",
    )


def _media_target_from_item(document, category, item, item_path: str) -> TrustedItemContext:
    current = item.image_url or item.source_image_url
    return _item_context(
        document=document,
        category=category,
        item=item,
        item_path=item_path,
        kind="media_handoff",
        current_value=current,
        field="image_url",
    )


def _targets_from_paths(
    *,
    document: CanonicalDocument,
    check_id: str,
    paths: list[str],
    strict: bool = True,
) -> list[TrustedItemContext]:
    kind = DRIVER_KIND.get(check_id)
    targets: list[TrustedItemContext] = []
    seen: set[str] = set()
    for raw in paths:
        path = raw.strip()
        if not path or path in seen:
            continue
        item_match = ITEM_PATH_RE.match(path)
        category_match = CATEGORY_PATH_RE.match(path)
        if check_id in DESCRIPTION_CHECK_IDS:
            if item_match is None:
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            located = _item_at(document, int(item_match.group(1)), int(item_match.group(2)), int(item_match.group(3)))
            if located is None:
                if strict:
                    raise ImprovementUnsupported(f"Path does not resolve on this catalogue: {path}")
                continue
            category, item, item_path = located
            if check_id == "missing_description" and not _description_blank(item.description):
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            ctx = _item_context(
                document=document,
                category=category,
                item=item,
                item_path=item_path,
                kind="description",
                current_value=item.description,
            )
            if ctx.path in seen:
                continue
            seen.add(ctx.path)
            targets.append(ctx)
            continue
        if check_id in CATEGORY_NAME_CHECK_IDS:
            if category_match is None:
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            located_cat = _category_at(document, int(category_match.group(1)), int(category_match.group(2)))
            if located_cat is None:
                if strict:
                    raise ImprovementUnsupported(f"Path does not resolve on this catalogue: {path}")
                continue
            category, category_path = located_cat
            if (category.name or "").strip():
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            ctx = _category_context(document=document, category=category, category_path=category_path)
            if ctx.path in seen:
                continue
            seen.add(ctx.path)
            targets.append(ctx)
            continue
        if check_id in CATALOGUE_STATE_DRIVERS or kind == "labels":
            if item_match is None:
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            located = _item_at(document, int(item_match.group(1)), int(item_match.group(2)), int(item_match.group(3)))
            if located is None:
                if strict:
                    raise ImprovementUnsupported(f"Path does not resolve on this catalogue: {path}")
                continue
            category, item, item_path = located
            ctx = _item_context(
                document=document,
                category=category,
                item=item,
                item_path=item_path,
                kind="labels",
                current_value=", ".join([str(label).strip() for label in item.labels if str(label).strip()]) or None,
                field="labels",
            )
            if ctx.path in seen:
                continue
            seen.add(ctx.path)
            targets.append(ctx)
            continue
        if check_id in MEDIA_HANDOFF_CHECK_IDS:
            if check_id == "no_images_present" and CATALOGUE_IMAGES_RE.match(path):
                ctx = TrustedItemContext(
                    path="catalogue.images",
                    kind="media_handoff",
                    name=document.restaurant_name,
                    category_name="",
                    current_value=None,
                    restaurant_name=document.restaurant_name,
                    needs_ollama=False,
                    media_type="image",
                )
                seen.add(ctx.path)
                targets.append(ctx)
                continue
            if VENUE_IMAGE_RE.match(path):
                ctx = TrustedItemContext(
                    path="venue.image_url",
                    kind="media_handoff",
                    name=document.restaurant_name,
                    category_name="",
                    current_value=document.venue.image_url,
                    restaurant_name=document.restaurant_name,
                    needs_ollama=False,
                    image_url=document.venue.image_url,
                    media_type="image",
                )
                seen.add(ctx.path)
                targets.append(ctx)
                continue
            if item_match is None:
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            located = _item_at(document, int(item_match.group(1)), int(item_match.group(2)), int(item_match.group(3)))
            if located is None:
                if strict:
                    raise ImprovementUnsupported(f"Path does not resolve on this catalogue: {path}")
                continue
            category, item, item_path = located
            ctx = _media_target_from_item(document, category, item, item_path)
            if ctx.path in seen:
                continue
            seen.add(ctx.path)
            targets.append(ctx)
            continue
        if check_id in ITEM_PRICE_CHECK_IDS:
            if item_match is None:
                if strict:
                    raise ImprovementUnsupported(f"Invalid or ineligible item/path: {path}")
                continue
            located = _item_at(document, int(item_match.group(1)), int(item_match.group(2)), int(item_match.group(3)))
            if located is None:
                if strict:
                    raise ImprovementUnsupported(f"Path does not resolve on this catalogue: {path}")
                continue
            category, item, item_path = located
            ctx = _price_target(document, item_path, item, category, strict=strict)
            if ctx is None:
                continue
            if ctx.path in seen:
                continue
            seen.add(ctx.path)
            targets.append(ctx)
    return targets


def _expand_finding(document: CanonicalDocument, finding: Finding) -> list[TrustedItemContext]:
    if finding.check_id == "missing_description" or finding.check_id == "description_coverage":
        from_paths = _targets_from_paths(
            document=document, check_id=finding.check_id, paths=finding.evidence.paths, strict=False
        )
        if from_paths:
            return from_paths
        return _missing_description_targets(document)
    if finding.check_id == "repeated_description":
        from_paths = _targets_from_paths(
            document=document, check_id=finding.check_id, paths=finding.evidence.paths, strict=False
        )
        if from_paths:
            return from_paths
        return _repeated_description_targets(document)
    if finding.check_id in {"placeholder_text", "malformed_text"}:
        return _targets_from_paths(
            document=document, check_id=finding.check_id, paths=finding.evidence.paths, strict=False
        )
    if finding.check_id in CATEGORY_NAME_CHECK_IDS:
        from_paths = _targets_from_paths(
            document=document, check_id=finding.check_id, paths=finding.evidence.paths, strict=False
        )
        if from_paths:
            return from_paths
        targets: list[TrustedItemContext] = []
        for menu_i, menu in enumerate(document.menus):
            for cat_i, category in enumerate(menu.categories):
                if not (category.name or "").strip():
                    targets.append(
                        _category_context(
                            document=document,
                            category=category,
                            category_path=f"menus[{menu_i}].categories[{cat_i}]",
                        )
                    )
        return targets
    if finding.check_id in MEDIA_HANDOFF_CHECK_IDS:
        if finding.check_id == "no_images_present":
            return [
                TrustedItemContext(
                    path="catalogue.images",
                    kind="media_handoff",
                    name=document.restaurant_name,
                    category_name="",
                    current_value=None,
                    restaurant_name=document.restaurant_name,
                    needs_ollama=False,
                    media_type="image",
                )
            ]
        paths = list(finding.evidence.paths)
        if not paths and finding.check_id == "missing_item_image":
            built: list[TrustedItemContext] = []
            for item_path, category, item in iter_menu_items(document):
                if not (item.image_url or item.source_image_url):
                    built.append(_media_target_from_item(document, category, item, item_path))
            return built
        return _targets_from_paths(document=document, check_id=finding.check_id, paths=paths, strict=False)
    if finding.check_id in ITEM_PRICE_CHECK_IDS:
        from_paths = _targets_from_paths(
            document=document, check_id=finding.check_id, paths=finding.evidence.paths, strict=False
        )
        if from_paths:
            return from_paths
        built = []
        for item_path, category, item in iter_menu_items(document):
            ctx = _price_target(document, item_path, item, category, strict=False)
            if ctx is not None:
                built.append(ctx)
        return built
    return []


def find_explanation_finding(explanation: GradeExplanation, check_id: str) -> Finding:
    matches = [finding for finding in explanation.findings if finding.check_id == check_id]
    if not matches:
        raise ImprovementUnsupported(f"No Phase 5 finding for check_id {check_id} on this revision.")
    return matches[0]


def resolve_targets(
    *,
    document: CanonicalDocument,
    explanation: GradeExplanation,
    check_id: str,
    requested_paths: list[str] | None,
) -> ResolvedImprovement:
    if check_id in UNSAFE_MENU_MOVE_CHECK_IDS:
        raise ImprovementUnsupported(
            f"{check_id} does not identify a source and destination for a menu move/order. "
            "Phase 6 will not invent a target category or order."
        )
    if check_id in UNSUPPORTED_INVENT_CHECK_IDS:
        raise ImprovementUnsupported(
            "Cannot invent an item name from empty trusted context. missing_item_name is not a Phase 6 generator target."
        )
    if check_id not in V1_SUPPORTED_DRIVERS:
        raise ImprovementUnsupported(f"{check_id} is not a Phase 6 improvement driver.")
    kind = DRIVER_KIND[check_id]
    if kind not in KIND_REGISTRY:
        raise ImprovementUnsupported(f"{check_id} is not a Phase 6 improvement driver.")
    if requested_paths is not None:
        if len(requested_paths) > MAX_LINES_PER_REQUEST:
            raise TooManyImprovementPaths(
                f"At most {MAX_LINES_PER_REQUEST} improvement paths may be requested at once."
            )
        if len(requested_paths) == 0:
            raise ImprovementUnsupported("Requested paths must not be empty when provided.")
    if check_id in CATALOGUE_STATE_DRIVERS:
        if requested_paths is None:
            targets = _empty_label_targets(document)
        else:
            targets = _targets_from_paths(
                document=document, check_id=check_id, paths=requested_paths, strict=True
            )
            if len(requested_paths) == 1 and len(targets) > 1:
                raise ImprovementUnsupported("Individual improvement request must target exactly one item.")
        if not targets:
            raise ImprovementUnsupported("No items without labels are eligible on this revision.")
        return ResolvedImprovement(
            check_id=check_id,
            finding_id="catalogue_state:empty_item_labels",
            why="Add catalogue labels for items that currently have none, without changing grading.v1.",
            targets=targets if requested_paths is not None else targets[:MAX_LINES_PER_REQUEST],
        )
    matches = [f for f in explanation.findings if f.check_id == check_id]
    if matches:
        finding = matches[0]
        finding_id = finding.finding_id
        why = finding.recommendation.action if finding.recommendation else finding.why
    else:
        finding_id = f"item_quality:{check_id}"
        why = f"Improve {kind}."
    if requested_paths is not None:
        targets = _targets_from_paths(
            document=document, check_id=check_id, paths=requested_paths, strict=True
        )
        if not targets:
            raise ImprovementUnsupported(f"None of the requested paths are eligible for {check_id}.")
        if len(requested_paths) == 1 and len(targets) > 1:
            raise ImprovementUnsupported("Individual improvement request must target exactly one item.")
    else:
        if not matches:
            raise ImprovementUnsupported(f"No Phase 5 finding for check_id {check_id} on this revision.")
        targets = _expand_finding(document, matches[0])
        if not targets:
            raise ImprovementUnsupported(f"No eligible Phase 6 lines for {check_id} on this revision.")
        targets = targets[:MAX_LINES_PER_REQUEST]
    return ResolvedImprovement(
        check_id=check_id,
        finding_id=finding_id,
        why=why,
        targets=targets,
    )
