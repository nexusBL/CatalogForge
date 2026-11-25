"""Phase 8 review-intelligence contract.

Official: first-party customer feedback intelligence. No catalogue mutation.
Engine: review_intel.v1.1 (aspect-level signals).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ENGINE_VERSION = "review_intel.v1.1"
ANALYSIS_CONTRACT = "signals.v1"
ALLOWED_INGEST_SOURCE = "supplied"
CUSTOMER_INGEST_SOURCE = "customer"
COLLECTION_SOURCE_STATUS = "unresolved"
RECURRENCE_THRESHOLD = 2

MAX_REVIEWS_PER_COLLECT = 200
MAX_REVIEW_CHARS = 8_000
MAX_EXTERNAL_ID_CHARS = 128
MAX_AUTHOR_KEY_CHARS = 128
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 50
MAX_STORED_REVIEWS = 1_000
CLAIM_TTL_SECONDS = 60.0

LinkageStatus = Literal["exact", "normalized", "ambiguous", "no_match"]
AnalysisStatus = Literal["GENERATING", "READY", "FAILED", "STALE"]
IngestSource = Literal["supplied", "customer"]
FeedbackTarget = Literal[
    "product_item",
    "catalogue_menu",
    "website_ux",
    "restaurant_service",
    "other",
]
RequestKind = Literal["none", "improvement_request"]
Polarity = Literal["positive", "negative", "neutral", "mixed"]
AspectName = Literal["taste", "quantity", "value", "service", "catalogue_info", "website_ux", "other"]
FeedbackIntent = Literal["observation", "praise", "complaint", "mixed"]
RecurrenceLabel = Literal["one_off", "repeated", "recurring_complaint"]
PositiveThemeLabel = Literal["none", "positive_theme"]
ObservationKind = Literal[
    "item_feedback",
    "unmatched_feedback",
    "catalogue_feedback",
    "website_feedback",
    "service_feedback",
]


class ReviewIngestItem(BaseModel):
    body: str
    external_id: str | None = None
    posted_at: str | None = None
    author_key: str | None = None
    observed_rating: float | None = None
    source: Literal["supplied"] = ALLOWED_INGEST_SOURCE

    @field_validator("body")
    @classmethod
    def body_present(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("review body is required")
        if len(text) > MAX_REVIEW_CHARS:
            raise ValueError("review body exceeds the Phase 8 size limit")
        return text

    @field_validator("external_id")
    @classmethod
    def external_id_limit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > MAX_EXTERNAL_ID_CHARS:
            raise ValueError("external_id exceeds the Phase 8 size limit")
        return text

    @field_validator("author_key")
    @classmethod
    def author_key_limit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > MAX_AUTHOR_KEY_CHARS:
            raise ValueError("author_key exceeds the Phase 8 size limit")
        return text

    @field_validator("posted_at")
    @classmethod
    def posted_at_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("observed_rating")
    @classmethod
    def finite_rating(cls, value: float | None) -> float | None:
        if value is None:
            return None
        number = float(value)
        if number != number or number in {float("inf"), float("-inf")}:
            raise ValueError("observed_rating must be a finite number")
        return number


class CustomerFeedbackRequest(BaseModel):
    body: str
    external_id: str | None = None
    observed_rating: float | None = None

    @field_validator("body")
    @classmethod
    def body_present(cls, value: str) -> str:
        return ReviewIngestItem.body_present(value)

    @field_validator("external_id")
    @classmethod
    def external_id_limit(cls, value: str | None) -> str | None:
        return ReviewIngestItem.external_id_limit(value)

    @field_validator("observed_rating")
    @classmethod
    def finite_rating(cls, value: float | None) -> float | None:
        return ReviewIngestItem.finite_rating(value)


class ReviewCollectRequest(BaseModel):
    reviews: list[ReviewIngestItem]

    @field_validator("reviews")
    @classmethod
    def bounded_batch(cls, value: list[ReviewIngestItem]) -> list[ReviewIngestItem]:
        if not value:
            raise ValueError("at least one review is required")
        if len(value) > MAX_REVIEWS_PER_COLLECT:
            raise ValueError("review batch exceeds the Phase 8 size limit")
        return value


class StoredReview(BaseModel):
    id: str
    catalogue_id: str
    organization_id: str
    source: IngestSource
    external_id: str
    body: str
    posted_at: str | None = None
    author_key: str | None = None
    observed_rating: float | None = None
    photo_id: str | None = None
    created_at: str
    duplicate: bool = False


class ReviewCollectResponse(BaseModel):
    collection_source: Literal["unresolved"] = COLLECTION_SOURCE_STATUS
    ingest_mode: IngestSource = ALLOWED_INGEST_SOURCE
    accepted: int
    duplicate: int
    reviews: list[StoredReview]


class CustomerFeedbackResponse(BaseModel):
    collection_source: Literal["unresolved"] = COLLECTION_SOURCE_STATUS
    ingest_mode: Literal["customer"] = CUSTOMER_INGEST_SOURCE
    duplicate: bool = False
    review: StoredReview


class ReviewListResponse(BaseModel):
    collection_source: Literal["unresolved"] = COLLECTION_SOURCE_STATUS
    ingest_mode: IngestSource | Literal["mixed"] = ALLOWED_INGEST_SOURCE
    total: int
    offset: int
    limit: int
    reviews: list[StoredReview]


class CatalogueItemRef(BaseModel):
    item_id: str | None = None
    name: str
    path: str
    category_name: str | None = None


class ReviewLinkage(BaseModel):
    status: LinkageStatus
    item_id: str | None = None
    item_name: str | None = None
    path: str | None = None
    span_text: str | None = None
    candidate_item_ids: list[str] = Field(default_factory=list)


class ReviewEvidence(BaseModel):
    review_id: str
    posted_at: str | None = None
    span_text: str | None = None
    observed_rating: float | None = None
    photo_id: str | None = None
    target: FeedbackTarget = "other"
    request_kind: RequestKind = "none"
    intent: FeedbackIntent = "observation"
    aspect: AspectName = "other"
    polarity: Polarity = "neutral"
    polarity_status: Polarity = "neutral"
    aspect_status: AspectName = "other"
    linkage: ReviewLinkage


class ReviewObservation(BaseModel):
    observation_id: str
    kind: ObservationKind
    target: FeedbackTarget = "other"
    request_kind: RequestKind = "none"
    intent: FeedbackIntent = "observation"
    aspect: AspectName = "other"
    polarity: Polarity = "neutral"
    item_id: str | None = None
    item_name: str | None = None
    path: str | None = None
    linkage_status: LinkageStatus
    review_count: int
    observed_ratings: list[float] = Field(default_factory=list)
    polarity_status: Polarity = "neutral"
    aspect_status: AspectName = "other"
    recurrence_status: RecurrenceLabel = "one_off"
    positive_theme_status: PositiveThemeLabel = "none"
    evidence: list[ReviewEvidence] = Field(default_factory=list)


class ReviewRecommendation(BaseModel):
    recommendation_id: str
    observation_id: str
    action: str
    target: FeedbackTarget = "other"
    request_kind: RequestKind = "none"
    intent: FeedbackIntent = "observation"
    aspect: AspectName = "other"
    polarity: Polarity = "neutral"
    recurrence_status: RecurrenceLabel = "one_off"
    positive_theme_status: PositiveThemeLabel = "none"
    evidence_review_ids: list[str] = Field(default_factory=list)


class ReviewIntelligence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    catalogue_id: str
    organization_id: str
    engine_version: str = ENGINE_VERSION
    source_head_revision: int
    source_state_hash: str
    reviews_fingerprint: str
    status: AnalysisStatus
    collection_source: Literal["unresolved"] = COLLECTION_SOURCE_STATUS
    polarity_status: Polarity = "neutral"
    aspect_status: Literal["ok"] = "ok"
    recurrence_status: RecurrenceLabel = "one_off"
    positive_theme_status: PositiveThemeLabel = "none"
    review_count: int
    observations: list[ReviewObservation] = Field(default_factory=list)
    recommendations: list[ReviewRecommendation] = Field(default_factory=list)
    created_at: str
    updated_at: str
    idempotent_replay: bool = False
    failure_reason: str | None = None

    @field_validator("polarity_status", mode="before")
    @classmethod
    def coerce_polarity(cls, value: object) -> object:
        return "neutral" if value == "unresolved" else value

    @field_validator("aspect_status", mode="before")
    @classmethod
    def coerce_aspect_contract(cls, value: object) -> object:
        if value in {None, "unresolved"}:
            return "ok"
        return value

    @field_validator("recurrence_status", mode="before")
    @classmethod
    def coerce_recurrence(cls, value: object) -> object:
        return "one_off" if value == "unresolved" else value

    @field_validator("positive_theme_status", mode="before")
    @classmethod
    def coerce_theme(cls, value: object) -> object:
        return "none" if value == "unresolved" else value
