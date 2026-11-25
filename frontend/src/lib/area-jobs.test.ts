import { describe, expect, it } from "vitest";
import {
  CATALOGUE_PERMANENT_DELETE_CONFIRM,
  canDeleteDiscoveryJob,
  discoveryPercent,
  DISCOVERY_JOB_DELETE_CONFIRM,
  filterVenues,
  pageSlice,
  scrapeProgress,
  type DiscoveredVenueRow,
} from "@/lib/area-jobs";

const venues: DiscoveredVenueRow[] = Array.from({ length: 120 }, (_, index) => ({
  platform: index % 2 ? "zomato" : "swiggy",
  catalogue_type: index % 3 ? "dineout" : "restaurant",
  venue_url: `https://www.swiggy.com/city/x/item-rest${index}`,
  name: `Venue ${index}`,
  location: index % 2 ? "North" : "South",
  identity_key: `k-${index}`,
  status: index === 1 ? "failed" : "discovered",
  selected: true,
}));

describe("area job helpers", () => {
  it("filters and paginates large discovery sets without dropping backend rows", () => {
    const filtered = filterVenues(venues, { search: "Venue 1", platform: "all", type: "all", status: "all" });
    expect(filtered.length).toBeGreaterThan(10);
    expect(pageSlice(venues, 1)).toHaveLength(50);
    expect(pageSlice(venues, 3)).toHaveLength(20);
  });

  it("keeps platform and status filters independent", () => {
    const failed = filterVenues(venues, { status: "failed" });
    expect(failed).toHaveLength(1);
    const zomato = filterVenues(venues, { platform: "zomato", type: "restaurant" });
    const located = filterVenues(
      [
        { ...venues[0], location_match: "located_here" },
        { ...venues[1], location_match: "delivers_here" },
      ],
      { location_match: "located_here" },
    );
    expect(located).toHaveLength(1);
    expect(located[0].location_match).toBe("located_here");
  });

  it("reports scrape progress from job counts", () => {
    expect(discoveryPercent({ id: "1", organization_id: "o", platforms: ["swiggy"], catalogue_type: "restaurant", status: "awaiting_confirmation", venues: [] })).toBe(100);
    expect(scrapeProgress({ id: "1", organization_id: "o", platforms: ["swiggy"], catalogue_type: "restaurant", status: "scraping", venues: [], selected_count: 87, completed_count: 38, failed_count: 2, blocked_count: 1, skipped_count: 0 }).current).toBe(41);
  });

  it("requires confirmation copy for discovery-job vs catalogue deletion", () => {
    expect(canDeleteDiscoveryJob("failed")).toBe(true);
    expect(canDeleteDiscoveryJob("awaiting_confirmation")).toBe(true);
    expect(canDeleteDiscoveryJob("scraping")).toBe(false);
    expect(DISCOVERY_JOB_DELETE_CONFIRM).toBe("Delete this discovery job permanently?");
    expect(CATALOGUE_PERMANENT_DELETE_CONFIRM).toContain("Delete this catalogue permanently?");
    expect(CATALOGUE_PERMANENT_DELETE_CONFIRM).toContain("cannot be undone");
    expect(DISCOVERY_JOB_DELETE_CONFIRM).not.toBe(CATALOGUE_PERMANENT_DELETE_CONFIRM);
  });
});
