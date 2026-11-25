"""Phase 7 media contract. Provider-independent. Preview-only candidates."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MEDIA_ENGINE_VERSION = "media.v1"
PROVIDER_ID = "local.v1"
MAX_PROMPT_CHARS = 500
MAX_REFERENCES = 3
MAX_PIXELS = 20_000_000
MAX_EDGE_PX = 4096
# Engineering cap for local I2V frames (not a product duration/SLA rule).
MAX_VIDEO_EDGE_PX = 1024
WAIT_SECONDS = 30.0

MediaStatus = Literal["GENERATING", "READY", "FAILED", "CANCELLED", "STALE", "APPLIED"]
MediaKind = Literal["image", "video"]
ArtifactKind = Literal["original", "candidate", "video"]

MediaOperation = Literal[
    "generate_image",
    "enhance",
    "background_removal",
    "background_generation",
    "blur",
    "crop",
    "expand",
    "cleanup",
    "edit",
    "image_to_video",
]

OPERATIONS_REQUIRING_SOURCE = frozenset(
    {
        "enhance",
        "background_removal",
        "background_generation",
        "blur",
        "crop",
        "expand",
        "cleanup",
        "edit",
        "image_to_video",
    }
)
class CropParams(BaseModel):
    left: float = 0.1
    top: float = 0.1
    right: float = 0.9
    bottom: float = 0.9


class BlurParams(BaseModel):
    radius: float = 4.0


class ExpandParams(BaseModel):
    left: int = 16
    top: int = 16
    right: int = 16
    bottom: int = 16


class MediaJobRequest(BaseModel):
    path: str
    operation: MediaOperation
    prompt: str | None = None
    proposal_id: str | None = None
    parent_candidate_id: str | None = None
    revision_ordinal: int | None = None
    crop: CropParams | None = None
    blur: BlurParams | None = None
    expand: ExpandParams | None = None

    @field_validator("path")
    @classmethod
    def path_present(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("path is required")
        return stripped


class PromptAssistRequest(BaseModel):
    path: str
    kind: Literal["edit", "image_to_video"] = "edit"
    prompt: str | None = None


class RevertRequest(BaseModel):
    to: Literal["original"] | str = "original"


class MediaCandidate(BaseModel):
    id: str
    parent_id: str | None = None
    operation: MediaOperation
    prompt: str | None = None
    artifact_id: str
    content_type: str
    media_kind: MediaKind
    provider: str = PROVIDER_ID
    created_at: str


class MediaJob(BaseModel):
    id: str
    catalogue_id: str
    organization_id: str
    path: str
    operation: MediaOperation
    status: MediaStatus
    prompt: str | None = None
    proposal_id: str | None = None
    source_head_revision: int
    source_state_hash: str
    source_ref: str | None = None
    source_snapshot_hash: str | None = None
    original_artifact_id: str | None = None
    active_candidate_id: str | None = None
    candidates: list[MediaCandidate] = Field(default_factory=list)
    reference_paths: list[str] = Field(default_factory=list)
    error: str | None = None
    idempotent_replay: bool = False
    created_at: str
    updated_at: str
    media_engine_version: str = MEDIA_ENGINE_VERSION


class MediaWorkspaceItem(BaseModel):
    path: str
    name: str
    description: str | None = None
    category_name: str
    image_url: str | None = None
    has_usable_image: bool
    active_job_id: str | None = None
    active_candidate_id: str | None = None


class MediaReference(BaseModel):
    path: str
    image_url: str
    name: str
    category_name: str
    reason: str


class MediaStudioResponse(BaseModel):
    catalogue_id: str
    restaurant_name: str | None = None
    source_head_revision: int
    source_state_hash: str
    items: list[MediaWorkspaceItem]
    references: list[MediaReference]
    jobs: list[MediaJob]
    handoff_path: str | None = None
    handoff_check_id: str | None = None


class PromptAssistResponse(BaseModel):
    suggested_prompt: str
    kind: str
    editable: bool = True


class MediaJobListResponse(BaseModel):
    jobs: list[MediaJob]


class MediaApplyResult(BaseModel):
    job: MediaJob
    catalogue_url: str
    grade_letter: str | None = None
    grade_score: float | None = None
