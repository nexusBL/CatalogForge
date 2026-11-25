from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from scraper.platform import infer_legacy_platform, platform_url_error

ExtractionStatus = Literal["ok", "partial", "blocked", "failed", "pending"]
PlatformName = Literal["swiggy", "zomato", "magicpin"]


class AuthUser(BaseModel):
    id: str
    email: str


class CatalogCreateRequest(BaseModel):
    restaurant_name: str = Field(min_length=1)
    fssai_number: str = ""
    swiggy_url: str = Field(min_length=1)
    source_url: str | None = None
    dineout_url: str | None = None
    organization_id: str = Field(min_length=1)
    catalogue_type: Literal["restaurant", "dineout", "both"] = "restaurant"
    platform: PlatformName = "swiggy"

    @model_validator(mode="before")
    @classmethod
    def alias_source_url(cls, data: Any) -> Any:
        if isinstance(data, dict) and not str(data.get("swiggy_url") or "").strip() and data.get("source_url"):
            data = {**data, "swiggy_url": data.get("source_url")}
        return data

    @field_validator("restaurant_name", "swiggy_url")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("fssai_number")
    @classmethod
    def strip_fssai(cls, value: str | None) -> str:
        return (value or "").strip()

    @field_validator("organization_id")
    @classmethod
    def strip_organization_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("dineout_url", "source_url")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def require_fields_for_type(self) -> CatalogCreateRequest:
        str(HttpUrl(self.swiggy_url))
        platform = infer_legacy_platform(self.swiggy_url, self.platform)
        mismatch = platform_url_error(platform, self.swiggy_url)
        if mismatch:
            raise ValueError(mismatch)
        if self.dineout_url:
            str(HttpUrl(self.dineout_url))
            dineout_mismatch = platform_url_error(platform, self.dineout_url)
            if dineout_mismatch:
                raise ValueError(dineout_mismatch)
        if self.catalogue_type in {"restaurant", "both"} and not self.fssai_number:
            raise ValueError("FSSAI license number is required for restaurant catalogues")
        if self.catalogue_type == "both" and not self.dineout_url:
            raise ValueError("Dineout URL is required when creating both catalogues")
        object.__setattr__(self, "platform", platform)
        if not self.source_url:
            object.__setattr__(self, "source_url", self.swiggy_url)
        return self


class CatalogCreateResponse(BaseModel):
    extraction_status: ExtractionStatus
    source_type: str | None = None
    restaurant_name: str
    fssai_number: str
    source_url: str
    platform: PlatformName = "swiggy"
    catalogue_type: Literal["restaurant", "dineout", "both"] = "restaurant"
    restaurant: dict[str, Any] | None = None
    dineout: dict[str, Any] | None = None
    categories: list[dict[str, Any]] = Field(default_factory=list)
    item_count: int = 0
    image_count: int = 0
    error: str | None = None
    access_method: str | None = None
    id: str | None = None
    organization_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    venue_id: str | None = None
    schema_version: int | None = None
    canonical: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None
    raw_capture_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_platform_field(cls, data: Any) -> Any:
        if isinstance(data, dict) and not str(data.get("platform") or "").strip():
            data = {**data, "platform": infer_legacy_platform(data.get("source_url"))}
        return data


class StoredCatalogue(BaseModel):
    id: str
    organization_id: str
    created_at: str
    result: CatalogCreateResponse
    head_revision: int | None = None
    state_hash: str | None = None


class CatalogueListResponse(BaseModel):
    catalogues: list[StoredCatalogue] = Field(default_factory=list)


class AreaJobCreateRequest(BaseModel):
    location: str = Field(min_length=1)
    platforms: list[PlatformName] = Field(min_length=1)
    catalogue_type: Literal["restaurant", "dineout", "both"] = "restaurant"
    organization_id: str = Field(min_length=1)
    max_venues: int | None = None
    concurrency: int = 1
    max_retries: int = 2
    delay_seconds: float = 0.0
    magicpin_dining: Literal["all", "budget", "fine"] = "budget"

    @field_validator("location", "organization_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value: list[PlatformName]) -> list[PlatformName]:
        names = list(dict.fromkeys(value))
        if not names:
            raise ValueError("Select at least one platform.")
        return names

    @field_validator("max_venues")
    @classmethod
    def optional_limit(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1:
            raise ValueError("Maximum venues must be at least 1 when a custom limit is set.")
        return value

    @field_validator("concurrency")
    @classmethod
    def concurrency_floor(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Concurrency must be at least 1.")
        return value


class AreaJobStartRequest(BaseModel):
    organization_id: str = Field(min_length=1)
    selected_keys: list[str] | None = None
    existing_actions: dict[str, Literal["skip", "rescrape", "update"]] | None = None


class AreaJobActionRequest(BaseModel):
    organization_id: str = Field(min_length=1)
