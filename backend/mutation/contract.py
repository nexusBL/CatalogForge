"""Phase 10 mutation contracts. Extra keys forbidden. Model-supplied IDs are ignored."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROPOSAL_TTL_SECONDS = 15 * 60
ENGINE_VERSION = "mutation.v1"

MutationOp = Literal[
    "add_item",
    "remove_item",
    "rename_item",
    "change_price",
    "update_description",
    "update_labels",
    "move_item",
    "improve_image",
    "generate_video",
]

MutationStatus = Literal["PENDING", "APPLIED", "CANCELLED", "STALE", "EXPIRED"]

PAYLOAD_OPS: frozenset[str] = frozenset(
    {
        "add_item",
        "remove_item",
        "rename_item",
        "change_price",
        "update_description",
        "update_labels",
        "move_item",
    }
)

MEDIA_OPS: frozenset[str] = frozenset({"improve_image", "generate_video"})


class MutationDraft(BaseModel):
    """Parsed owner request. Names only — never IDs from the model."""

    model_config = ConfigDict(extra="forbid")

    operation: MutationOp
    item_name: str | None = None
    new_item_name: str | None = None
    category_name: str | None = None
    source_category_name: str | None = None
    target_category_name: str | None = None
    price: float | int | None = None
    description: str | None = None
    labels: list[str] | None = None

    @field_validator("item_name", "new_item_name", "category_name", "source_category_name", "target_category_name", "description")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class OwnerCatalogueMutationRequest(BaseModel):
    """Direct owner edit from Manage Catalogue. Reuses mutation patch + history (not chat confirm)."""

    model_config = ConfigDict(extra="forbid")

    draft: MutationDraft
    item_id: str | None = None
    source_head_revision: int = Field(ge=0)
    source_state_hash: str = Field(min_length=1)

    @field_validator("item_id")
    @classmethod
    def strip_item_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("source_state_hash")
    @classmethod
    def strip_state_hash(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("source_state_hash is required")
        return text


class MutationConfirmRequest(BaseModel):
    confirm_token: str = Field(min_length=8)

    @field_validator("confirm_token")
    @classmethod
    def strip_token(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) < 8:
            raise ValueError("confirm_token is required")
        return text


class MutationProposalView(BaseModel):
    proposal_id: str
    confirm_token: str | None = None
    operation: MutationOp
    status: MutationStatus
    summary: str
    item_name: str | None = None
    category_name: str | None = None
    current_value: str | None = None
    proposed_value: str | None = None
    expires_at: str | None = None
    writes_payload: bool = True
    media_job_id: str | None = None
    candidates: list[str] = Field(default_factory=list)


class MutationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    confirm_token: str
    user_id: str
    organization_id: str
    catalogue_id: str
    operation: MutationOp
    status: MutationStatus
    source_head_revision: int
    source_state_hash: str
    item_id: str | None = None
    item_name: str | None = None
    category_name: str | None = None
    source_category_name: str | None = None
    target_category_name: str | None = None
    item_path: str | None = None
    current_value: str | None = None
    proposed_value: str | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
    writes_payload: bool = True
    media_job_id: str | None = None
    expires_at: str
    created_at: str
    updated_at: str
    engine_version: str = ENGINE_VERSION
