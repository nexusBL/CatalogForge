"""Phase 6 improvement contract. Downstream of frozen grade_explain.v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

IMPROVEMENT_VERSION = "improvement.v1"
MAX_LINES_PER_REQUEST = 5
MAX_DESCRIPTION_CHARS = 400
MAX_CATEGORY_NAME_CHARS = 80
MAX_LABEL_CHARS = 40
MAX_LABELS = 8

ProposalStatus = Literal["READY", "FAILED", "PARTIAL", "STALE", "APPLIED", "CANCELLED"]
LineStatus = Literal["READY", "FAILED"]
ImprovementKind = Literal["description", "category_name", "labels", "media_handoff", "item_price"]
MediaType = Literal["image", "video"]

DESCRIPTION_CHECK_IDS = frozenset(
    {
        "missing_description",
        "description_coverage",
        "placeholder_text",
        "malformed_text",
        "repeated_description",
    }
)
CATEGORY_NAME_CHECK_IDS = frozenset({"missing_category_name"})
MEDIA_HANDOFF_CHECK_IDS = frozenset(
    {
        "missing_item_image",
        "image_missing",
        "image_invalid",
        "image_unreadable",
        "image_low_quality",
        "no_images_present",
    }
)
ITEM_PRICE_CHECK_IDS = frozenset({"missing_price", "invalid_price"})
CATALOGUE_STATE_DRIVERS = frozenset({"empty_item_labels"})
UNSAFE_MENU_MOVE_CHECK_IDS = frozenset({"category_count_mismatch"})
UNSUPPORTED_INVENT_CHECK_IDS = frozenset({"missing_item_name"})

V1_PHASE5_CHECK_IDS = (
    DESCRIPTION_CHECK_IDS | CATEGORY_NAME_CHECK_IDS | MEDIA_HANDOFF_CHECK_IDS | ITEM_PRICE_CHECK_IDS
)
V1_SUPPORTED_DRIVERS = V1_PHASE5_CHECK_IDS | CATALOGUE_STATE_DRIVERS


class ImprovementLineRequest(BaseModel):
    check_id: str
    paths: list[str] | None = None
    instruction: str | None = None
    refining_proposal_id: str | None = None

    @field_validator("check_id")
    @classmethod
    def check_id_present(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("check_id is required")
        return stripped


class TrustedItemContext(BaseModel):
    path: str
    kind: ImprovementKind
    item_id: str | None = None
    name: str
    category_name: str
    food_type: str | None = None
    labels: list[str] = Field(default_factory=list)
    current_value: str | None = None
    restaurant_name: str | None = None
    needs_ollama: bool = True
    original_price: str | None = None
    image_url: str | None = None
    media_type: MediaType | None = None
    instruction: str | None = None
    current_proposal_value: str | None = None


class GeneratorCandidate(BaseModel):
    proposed_value: str = ""
    proposed_labels: list[str] | None = None
    model: str | None = None
    model_digest: str | None = None
    elapsed_ms: int | None = None
    raw_response: str | None = None


class MediaHandoff(BaseModel):
    phase7_required: bool = True
    media_type: MediaType = "image"
    capability: str = "image_improvement"
    current_ref: str | None = None


class ImprovementLine(BaseModel):
    path: str
    kind: ImprovementKind
    check_id: str
    finding_id: str
    current_value: str | None = None
    proposed_value: str | None = None
    proposed_labels: list[str] | None = None
    media_handoff: MediaHandoff | None = None
    status: LineStatus
    failure_reason: str | None = None
    why: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class ImprovementProposal(BaseModel):
    id: str
    catalogue_id: str
    organization_id: str
    source_head_revision: int
    source_state_hash: str
    check_id: str
    finding_id: str
    improvement_version: str = IMPROVEMENT_VERSION
    status: ProposalStatus
    lines: list[ImprovementLine]
    created_at: str
    idempotent_replay: bool = False


class ImprovementApplyResult(BaseModel):
    proposal: ImprovementProposal
    applied_paths: list[str] = Field(default_factory=list)
    skipped_media_paths: list[str] = Field(default_factory=list)
    grade_letter: str | None = None
    grade_score: float | None = None


class ImprovementListResponse(BaseModel):
    proposals: list[ImprovementProposal]


class ResolvedImprovement(BaseModel):
    check_id: str
    finding_id: str
    why: str
    targets: list[TrustedItemContext]
