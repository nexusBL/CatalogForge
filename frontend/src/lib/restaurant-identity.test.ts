import { describe, expect, it } from "vitest";
import {
  catalogueMatchesDomain,
  dineoutAboutFields,
  outletIdentity,
  overviewStats,
  plausibleVenueDistance,
  restaurantAboutFields,
  restaurantDisplayName,
  restaurantLocation,
  venueDisplayName,
} from "@/lib/restaurant-identity";
import type { StoredCatalogue } from "@/lib/catalog-types";

describe("restaurant identity", () => {
  it("distinguishes branches by location instead of name alone", () => {
    expect(restaurantDisplayName({ name: "Barbeque Nation" }, "fallback")).toBe("Barbeque Nation");
    expect(restaurantDisplayName(undefined, undefined)).toBe("Restaurant");
    expect(restaurantDisplayName({ name: "  " }, undefined)).toBe("Restaurant");
    expect(restaurantLocation({ outlet: "Kankanady, Mangalore" })).toBe("Kankanady, Mangalore");
    expect(restaurantLocation({ address: "MG Road" })).toBe("MG Road");
    expect(outletIdentity("Bangalore Bagel Shop", "Sivanchetti Gardens, Central Bangalore")).not.toBe(
      outletIdentity("Bangalore Bagel Shop", "Indiranagar, Bangalore"),
    );
  });

  it("hides missing optional about fields instead of showing Not available", () => {
    const fields = restaurantAboutFields({
      restaurant: { name: "Barbeque Nation", address: "Kankanady" },
      sourceUrl: "https://www.swiggy.com/x",
    });
    const labels = fields.map((field) => field.label);
    expect(labels).toEqual(["Restaurant Name", "Address", "Swiggy URL"]);
    expect(labels.join(" ")).not.toContain("Zomato");
    expect(labels.join(" ")).not.toContain("Magicpin");
    expect(JSON.stringify(fields)).not.toContain("Not available");
    expect(fields.find((field) => field.label === "Swiggy URL")?.href).toBe("https://www.swiggy.com/x");
  });

  it("never labels a Zomato source URL as Swiggy URL", () => {
    const fields = restaurantAboutFields({
      restaurant: { name: "Street Storyss", zomato_url: "https://www.zomato.com/bangalore/street-storyss" },
      sourceUrl: "https://www.zomato.com/bangalore/street-storyss",
    });
    const labels = fields.map((field) => field.label);
    expect(labels).toContain("Zomato URL");
    expect(labels).not.toContain("Swiggy URL");
    expect(fields.find((field) => field.label === "Zomato URL")?.href).toBe(
      "https://www.zomato.com/bangalore/street-storyss",
    );
  });

  it("does not use kilometre strings as location or address", () => {
    expect(restaurantLocation({ outlet: "2.4 km", address: "Indiranagar, Bengaluru" })).toBe("Indiranagar, Bengaluru");
    expect(restaurantLocation({ outlet: "1.8 km away" })).toBeNull();
    const fields = restaurantAboutFields({
      restaurant: { name: "Live Kitchen", outlet: "2.4 km", address: "5 km" },
      sourceUrl: "https://www.swiggy.com/city/bangalore/live-kitchen-rest1",
    });
    expect(fields.map((field) => field.label)).toEqual(["Restaurant Name", "Swiggy URL"]);
  });

  it("keeps address when outlet differs from street address", () => {
    const fields = restaurantAboutFields({
      restaurant: { name: "Bangalore Bagel Shop", outlet: "Sivanchetti Gardens", address: "12, Sivanchetti Gardens" },
    });
    expect(fields.map((field) => field.label)).toEqual(["Restaurant Name", "Address"]);
  });

  it("classifies restaurant, dineout, and both catalogues", () => {
    expect(catalogueMatchesDomain({ extraction_status: "ok", restaurant_name: "A", fssai_number: "1", source_url: "https://swiggy.com/x" }, "restaurant")).toBe(true);
    expect(catalogueMatchesDomain({ extraction_status: "ok", restaurant_name: "A", fssai_number: "1", source_url: "https://swiggy.com/x", catalogue_type: "dineout" }, "restaurant")).toBe(false);
    expect(catalogueMatchesDomain({ extraction_status: "ok", restaurant_name: "A", fssai_number: "1", source_url: "https://swiggy.com/x", catalogue_type: "both" }, "dineout")).toBe(true);
  });

  it("omits missing dineout about fields", () => {
    const fields = dineoutAboutFields({ venue: "Daffy's Brewgarden", location: { locality: "Indiranagar" } });
    expect(fields.map((field) => field.label)).toEqual(["Restaurant name", "Location"]);
    expect(JSON.stringify(fields)).not.toContain("FSSAI");
    expect(JSON.stringify(fields)).not.toContain("null");
  });

  it("omits implausible viewer distances", () => {
    expect(plausibleVenueDistance("1.2 km")).toBe("1.2 km");
    expect(plausibleVenueDistance("200 m")).toBe("200 m");
    expect(plausibleVenueDistance("349.5 km")).toBeNull();
    expect(plausibleVenueDistance("null")).toBeNull();
  });

  it("computes overview statistics from stored catalogues", () => {
    const rows: StoredCatalogue[] = [
      {
        id: "1",
        organizationId: "org",
        createdAt: "2026-01-01T00:00:00Z",
        result: {
          extraction_status: "ok",
          restaurant_name: "A",
          fssai_number: "1",
          source_url: "https://swiggy.com/a",
          catalogue_type: "restaurant",
          item_count: 10,
          image_count: 4,
        },
      },
      {
        id: "2",
        organizationId: "org",
        createdAt: "2026-01-02T00:00:00Z",
        result: {
          extraction_status: "ok",
          restaurant_name: "B",
          fssai_number: "",
          source_url: "https://swiggy.com/b",
          catalogue_type: "dineout",
          item_count: 0,
          image_count: 6,
        },
      },
    ];
    expect(overviewStats(rows)).toEqual({
      total: 2,
      restaurant: 1,
      dineout: 1,
      both: 0,
      swiggy: 2,
      zomato: 0,
      magicpin: 0,
      items: 10,
      images: 10,
    });
    expect(venueDisplayName(rows[1].result)).toBe("B");
  });

  it("treats same restaurant name with different outlets as separate identities", () => {
    expect(outletIdentity("Daffy's Brewgarden", "Indiranagar")).not.toBe(
      outletIdentity("Daffy's Brewgarden", "Koramangala"),
    );
  });
});
