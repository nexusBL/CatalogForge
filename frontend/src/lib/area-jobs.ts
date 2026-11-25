export type AreaJobStatus =
  | "created"
  | "discovering"
  | "awaiting_confirmation"
  | "queued"
  | "scraping"
  | "completed"
  | "partially_completed"
  | "failed"
  | "cancelled";

export type AreaVenueStatus =
  | "discovered"
  | "selected"
  | "queued"
  | "scraping"
  | "completed"
  | "failed"
  | "blocked"
  | "skipped";

export type LocationMatch = "located_here" | "delivers_here" | "unknown";

export type DiscoveredVenueRow = {
  platform: "swiggy" | "zomato" | "magicpin";
  catalogue_type: "restaurant" | "dineout";
  venue_url: string;
  canonical_url?: string | null;
  venue_id?: string | null;
  name?: string | null;
  location?: string | null;
  address?: string | null;
  rating?: string | null;
  image_url?: string | null;
  identity_key?: string | null;
  status: AreaVenueStatus;
  selected?: boolean;
  existing_catalogue_id?: string | null;
  existing_action?: "skip" | "rescrape" | "update" | null;
  catalogue_id?: string | null;
  error?: string | null;
  scraping_started_at?: string | null;
  discovery_scope?: "delivery_to_location" | "physical_location" | null;
  location_match?: LocationMatch | null;
};

export type AreaJob = {
  id: string;
  organization_id: string;
  location_input?: string;
  normalized_location?: string;
  location?: {
    original?: string;
    normalized?: string;
    city?: string | null;
    state?: string | null;
    locality?: string | null;
    country?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    display_name?: string | null;
    confidence?: string | null;
  };
  platforms: Array<"swiggy" | "zomato" | "magicpin">;
  catalogue_type: "restaurant" | "dineout" | "both";
  status: AreaJobStatus;
  venues: DiscoveredVenueRow[];
  discovered_count?: number;
  selected_count?: number;
  completed_count?: number;
  failed_count?: number;
  blocked_count?: number;
  skipped_count?: number;
  remaining_count?: number;
  located_here_count?: number;
  delivers_here_count?: number;
  unknown_location_count?: number;
  discovery_scope?: "delivery_to_location" | "physical_location" | null;
  error?: string | null;
  options?: {
    max_venues?: number | null;
    concurrency?: number;
    max_retries?: number;
  };
};

export const DISCOVERY_JOB_DELETE_CONFIRM = "Delete this discovery job permanently?";
export const CATALOGUE_PERMANENT_DELETE_CONFIRM =
  "Delete this catalogue permanently? This will remove the catalogue and its stored data and cannot be undone.";

export function canDeleteDiscoveryJob(status: AreaJobStatus): boolean {
  return (
    status === "failed" ||
    status === "cancelled" ||
    status === "awaiting_confirmation" ||
    status === "completed" ||
    status === "partially_completed" ||
    status === "created"
  );
}

export const PAGE_SIZE = 50;

export function jobLocation(job: AreaJob): string {
  return job.location?.normalized || job.normalized_location || job.location_input || job.location?.original || "";
}

export function filterVenues(
  venues: DiscoveredVenueRow[],
  query: {
    search?: string;
    platform?: string;
    type?: string;
    status?: string;
    location_match?: string;
  },
): DiscoveredVenueRow[] {
  const search = (query.search || "").trim().toLowerCase();
  return venues.filter((venue) => {
    if (query.platform && query.platform !== "all" && venue.platform !== query.platform) {
      return false;
    }
    if (query.type && query.type !== "all" && venue.catalogue_type !== query.type) {
      return false;
    }
    if (query.status && query.status !== "all" && venue.status !== query.status) {
      return false;
    }
    if (query.location_match && query.location_match !== "all" && (venue.location_match || "unknown") !== query.location_match) {
      return false;
    }
    if (!search) {
      return true;
    }
    const haystack = `${venue.name || ""} ${venue.location || ""} ${venue.venue_url}`.toLowerCase();
    return haystack.includes(search);
  });
}

export function pageSlice<T>(items: T[], page: number, size = PAGE_SIZE): T[] {
  const start = Math.max(0, (page - 1) * size);
  return items.slice(start, start + size);
}

export function discoveryPercent(job: AreaJob): number {
  if (job.status === "awaiting_confirmation" || job.status === "queued" || job.status === "scraping" || job.status === "completed" || job.status === "partially_completed") {
    return 100;
  }
  if (job.status === "discovering") {
    return 50;
  }
  return 0;
}

export function locationMatchLabel(match?: LocationMatch | null): string {
  if (match === "located_here") {
    return "Located here";
  }
  if (match === "delivers_here") {
    return "Delivers here";
  }
  return "Location unknown";
}

export function scrapeProgress(job: AreaJob): { current: number; total: number } {
  const total = job.selected_count ?? job.venues.filter((item) => item.selected !== false).length;
  const current = (job.completed_count || 0) + (job.failed_count || 0) + (job.blocked_count || 0) + (job.skipped_count || 0);
  return { current, total };
}
