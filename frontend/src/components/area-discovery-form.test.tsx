import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AreaDiscoveryForm } from "@/components/area-discovery-form";
import { AreaJobView } from "@/components/area-job-view";
import type { AreaJob } from "@/lib/area-jobs";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
}));

const job: AreaJob = {
  id: "job-1",
  organization_id: "org_1",
  location: { original: "Harbour Town", normalized: "Harbour Town" },
  platforms: ["swiggy"],
  catalogue_type: "restaurant",
  status: "awaiting_confirmation",
  discovery_scope: "delivery_to_location",
  located_here_count: 2,
  delivers_here_count: 0,
  unknown_location_count: 0,
  venues: [
    {
      platform: "swiggy",
      catalogue_type: "restaurant",
      venue_url: "https://www.swiggy.com/city/harbour-town/alpha-rest1",
      name: "Alpha Kitchen",
      location: "Harbour Town",
      identity_key: "swiggy:restaurant:id:1",
      status: "discovered",
      selected: true,
    },
    {
      platform: "swiggy",
      catalogue_type: "restaurant",
      venue_url: "https://www.swiggy.com/city/harbour-town/beta-rest2",
      name: "Beta Bistro",
      location: "Harbour Town",
      identity_key: "swiggy:restaurant:id:2",
      status: "discovered",
      selected: true,
      existing_catalogue_id: "cat-old",
      existing_action: "skip",
    },
  ],
};

describe("area discovery UI", () => {
  it("collects any location and defaults to all available venues", () => {
    const html = renderToStaticMarkup(<AreaDiscoveryForm organizationId="org_1" />);
    expect(html).toContain("typed into the location search, then the matching suggestion is selected");
    expect(html).toContain("All available");
    expect(html).toContain("Swiggy");
    expect(html).toContain("Zomato");
    expect(html).toContain("Magicpin");
    expect(html).toContain("All available");
    expect(html).toContain("Swiggy homepage location");
    expect(html).toContain("Magicpin Search Location");
  });

  it("reviews discovered venues before scraping", () => {
    const html = renderToStaticMarkup(<AreaJobView job={job} organizationId="org_1" />);
    expect(html).toContain("Harbour Town");
    expect(html).toContain("Discovered: 2 venues");
    expect(html).toContain("Located here");
    expect(html).toContain("Delivers here");
    expect(html).toContain("Location unknown");
    expect(html).toContain("Alpha Kitchen");
    expect(html).toContain("Already exists");
    expect(html).toContain("Select All");
    expect(html).toContain("Start Scraping");
  });
});
