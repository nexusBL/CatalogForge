"""Deterministic restaurant reference-image selection for missing-image generation."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.grading.document import iter_menu_items
from backend.media.contract import MAX_REFERENCES, MediaReference
from backend.media.source import is_usable_image_ref


def select_reference_images(
    document: CanonicalDocument,
    *,
    target_path: str,
    target_category: str,
) -> list[MediaReference]:
    """Prefer same-category usable item photos, then other menu photos, stable path order.

    Caps at MAX_REFERENCES. Does not include the target item. Does not include
    venue gallery dumps or veg/non-veg icons.
    """
    ranked: list[tuple[int, str, MediaReference]] = []
    for item_path, category, item in iter_menu_items(document):
        if item_path == target_path or f"{item_path}.image_url" == target_path:
            continue
        url = item.image_url or item.source_image_url
        if not is_usable_image_ref(url):
            continue
        same = 0 if (category.name or "").strip() == (target_category or "").strip() and target_category else 1
        ranked.append(
            (
                same,
                item_path,
                MediaReference(
                    path=f"{item_path}.image_url",
                    image_url=url or "",
                    name=item.name,
                    category_name=category.name,
                    reason="same_category" if same == 0 else "same_catalogue",
                ),
            )
        )
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in ranked[:MAX_REFERENCES]]
