from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PlatformName = Literal["swiggy", "zomato", "magicpin"]
CatalogueKind = Literal["restaurant", "dineout"]
VenueStatus = Literal[
    "discovered",
    "selected",
    "queued",
    "scraping",
    "completed",
    "failed",
    "blocked",
    "skipped",
]
JobStatus = Literal[
    "created",
    "discovering",
    "awaiting_confirmation",
    "queued",
    "scraping",
    "completed",
    "partially_completed",
    "failed",
    "cancelled",
]


@dataclass
class LocationQuery:
    original: str
    normalized: str
    city: str | None = None
    state: str | None = None
    locality: str | None = None
    slug: str = ""
    search_text: str = ""
    country: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    display_name: str | None = None
    confidence: str | None = None
    place_id: str | None = None
    platform_places: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveredVenue:
    platform: PlatformName
    catalogue_type: CatalogueKind
    venue_url: str
    canonical_url: str | None = None
    venue_id: str | None = None
    name: str | None = None
    location: str | None = None
    address: str | None = None
    rating: str | None = None
    source: str | None = None
    identity_key: str | None = None
    status: VenueStatus = "discovered"
    retry_count: int = 0
    error: str | None = None
    catalogue_id: str | None = None
    existing_catalogue_id: str | None = None
    existing_action: Literal["skip", "rescrape", "update"] | None = None
    image_url: str | None = None
    cuisine: str | None = None
    selected: bool = True
    next_attempt_at: str | None = None
    scraping_started_at: str | None = None
    discovery_scope: str | None = None
    location_match: str | None = None
    sub_source: str | None = None
    distance_km: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ListingPage:
    url: str
    html: str = ""
    payload: Any = None
    next_url: str | None = None
    has_more: bool = False
    exhausted: bool = False
    blocked: bool = False
    error: str | None = None


@dataclass
class DiscoveryOptions:
    max_venues: int | None = None
    max_pages: int | None = None
    max_retries: int = 2
    concurrency: int = 1
    delay_seconds: float = 0.0
    magicpin_dining: str = "budget"
    current_kind: CatalogueKind = "restaurant"
    geocoder: Any = None
    include_district: bool = False

    def __post_init__(self) -> None:
        if self.max_venues is not None and self.max_venues < 1:
            raise ValueError("Maximum venues must be at least 1 when a custom limit is set.")
        if self.concurrency < 1:
            raise ValueError("Concurrency must be at least 1.")
        if self.max_retries < 0:
            raise ValueError("Retry count cannot be negative.")


@dataclass
class AreaJob:
    id: str
    organization_id: str
    location: LocationQuery
    platforms: list[PlatformName]
    catalogue_type: Literal["restaurant", "dineout", "both"]
    status: JobStatus = "created"
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    options: DiscoveryOptions = field(default_factory=DiscoveryOptions)
    venues: list[DiscoveredVenue] = field(default_factory=list)
    error: str | None = None
    discovery_scope: str | None = None

    def counts(self) -> dict[str, int]:
        statuses = [item.status for item in self.venues]
        selected = [item for item in self.venues if item.selected]
        return {
            "discovered_count": len(self.venues),
            "selected_count": len(selected),
            "completed_count": sum(1 for item in statuses if item == "completed"),
            "failed_count": sum(1 for item in statuses if item == "failed"),
            "blocked_count": sum(1 for item in statuses if item == "blocked"),
            "skipped_count": sum(1 for item in statuses if item == "skipped"),
            "queued_count": sum(1 for item in statuses if item in {"queued", "discovered", "selected"}),
            "scraping_count": sum(1 for item in statuses if item == "scraping"),
            "remaining_count": sum(
                1
                for item in self.venues
                if item.selected and item.status in {"discovered", "selected", "queued", "scraping"}
            ),
            "located_here_count": sum(1 for item in self.venues if item.location_match == "located_here"),
            "delivers_here_count": sum(1 for item in self.venues if item.location_match == "delivers_here"),
            "unknown_location_count": sum(1 for item in self.venues if item.location_match == "unknown"),
        }
