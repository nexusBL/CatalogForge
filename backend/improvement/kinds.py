"""Allowlisted Phase 6 improvement kinds. Not an arbitrary JSON patch API."""

from __future__ import annotations

from dataclasses import dataclass

from backend.improvement.contract import ImprovementKind


@dataclass(frozen=True)
class KindSpec:
    kind: ImprovementKind
    eligibility: str
    canonical_path_pattern: str
    input_type: str
    proposed_output_type: str
    validation: str
    preview: str
    provenance: str
    apply: str = "never in Phase 6"


KIND_REGISTRY: dict[str, KindSpec] = {
    "description": KindSpec(
        kind="description",
        eligibility="Phase 5 description findings",
        canonical_path_pattern="menus[i].categories[j].items[k].description",
        input_type="str | None",
        proposed_output_type="str",
        validation="backend text/claim/ingredient checks",
        preview="current/proposed text",
        provenance="ollama candidate + validator",
    ),
    "category_name": KindSpec(
        kind="category_name",
        eligibility="Phase 5 missing_category_name",
        canonical_path_pattern="menus[i].categories[j].name",
        input_type="str",
        proposed_output_type="str",
        validation="backend text checks",
        preview="current/proposed name",
        provenance="ollama candidate + validator",
    ),
    "labels": KindSpec(
        kind="labels",
        eligibility="catalogue-state empty_item_labels (not a grading.v1 section)",
        canonical_path_pattern="menus[i].categories[j].items[k].labels",
        input_type="list[str]",
        proposed_output_type="list[str]",
        validation="preserve existing; reject claims/allergens/malformed",
        preview="current/proposed label lists",
        provenance="deterministic food_type and/or ollama labels",
    ),
    "media_handoff": KindSpec(
        kind="media_handoff",
        eligibility="Phase 5 vision/image findings",
        canonical_path_pattern="item/venue/catalogue image path",
        input_type="current media ref | empty",
        proposed_output_type="Phase 7 handoff record",
        validation="no generation; persist finding identity only",
        preview="current media problem → Phase 7 handoff",
        provenance="deterministic; no image/video model",
    ),
    "item_price": KindSpec(
        kind="item_price",
        eligibility="Phase 5 missing_price/invalid_price when original_price is trusted",
        canonical_path_pattern="menus[i].categories[j].items[k].price",
        input_type="number | None",
        proposed_output_type="number copied from original_price",
        validation="coerce_price; never LLM-invented",
        preview="current/proposed price",
        provenance="deterministic copy of original_price",
    ),
}

DRIVER_KIND: dict[str, ImprovementKind] = {
    "missing_description": "description",
    "description_coverage": "description",
    "placeholder_text": "description",
    "malformed_text": "description",
    "repeated_description": "description",
    "missing_category_name": "category_name",
    "empty_item_labels": "labels",
    "missing_item_image": "media_handoff",
    "image_missing": "media_handoff",
    "image_invalid": "media_handoff",
    "image_unreadable": "media_handoff",
    "image_low_quality": "media_handoff",
    "no_images_present": "media_handoff",
    "missing_price": "item_price",
    "invalid_price": "item_price",
}
