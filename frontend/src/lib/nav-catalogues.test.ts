import { describe, expect, it } from "vitest";
import type { StoredCatalogue } from "@/lib/catalog-types";
import {
  cataloguesForDomain,
  cataloguesHref,
  createCatalogueHref,
  filterStoredCatalogues,
  navCatalogueItem,
} from "@/lib/nav-catalogues";
import { outletIdentity } from "@/lib/restaurant-identity";

function row(id: string, result: Partial<StoredCatalogue["result"]>): StoredCatalogue {
  return {
    id,
    organizationId: "org",
    createdAt: "2026-01-01T00:00:00Z",
    result: {
      extraction_status: "ok",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "1",
      source_url: "https://www.swiggy.com/city/bangalore/daffys-rest1",
      restaurant: { name: "Daffy's Brewgarden", outlet: "Indiranagar, Bangalore" },
      ...result,
    },
  };
}

describe("nav catalogues", () => {
  const restaurant = row("r1", {
    catalogue_type: "restaurant",
    platform: "swiggy",
  });
  const dineout = row("d1", {
    catalogue_type: "dineout",
    platform: "zomato",
    source_url: "https://www.zomato.com/bangalore/daffys-brewgarden-indiranagar-bangalore",
    restaurant: { name: "Daffy's Brewgarden", outlet: "Indiranagar, Bangalore" },
  });
  const both = row("b1", {
    catalogue_type: "both",
    platform: "magicpin",
    source_url: "https://magicpin.in/Bangalore/Defence-Colony/Restaurant/Daffys-Brewgarden/store/5642c9",
    restaurant: { name: "Daffy's Brewgarden", outlet: "Defence Colony, Bangalore" },
  });
  const otherBranch = row("r2", {
    catalogue_type: "restaurant",
    platform: "swiggy",
    restaurant: { name: "Daffy's Brewgarden", outlet: "Koramangala, Bangalore" },
  });

  it("puts both catalogues under restaurant and dineout without duplicating the record id", () => {
    const restaurantRows = cataloguesForDomain([restaurant, dineout, both], "restaurant");
    const dineoutRows = cataloguesForDomain([restaurant, dineout, both], "dineout");
    expect(restaurantRows.map((item) => item.id)).toEqual(["r1", "b1"]);
    expect(dineoutRows.map((item) => item.id)).toEqual(["d1", "b1"]);
  });

  it("builds identity subtitles with location, platform, and type", () => {
    const item = navCatalogueItem(dineout);
    expect(item.name).toBe("Daffy's Brewgarden");
    expect(item.location).toBe("Indiranagar, Bangalore");
    expect(item.subtitle).toContain("Indiranagar");
    expect(item.subtitle).toContain("Zomato");
    expect(item.subtitle).toContain("Dineout");
    expect(item.identity).toBe(outletIdentity("Daffy's Brewgarden", "Indiranagar, Bangalore"));
    expect(navCatalogueItem(otherBranch).identity).not.toBe(item.identity);
  });

  it("filters by platform without inventing rows", () => {
    const rows = [restaurant, dineout, both];
    expect(filterStoredCatalogues(rows, { platform: "swiggy" }).map((item) => item.id)).toEqual(["r1"]);
    expect(filterStoredCatalogues(rows, { platform: "zomato" }).map((item) => item.id)).toEqual(["d1"]);
    expect(filterStoredCatalogues(rows, { platform: "magicpin" }).map((item) => item.id)).toEqual(["b1"]);
  });

  it("uses existing create and list routes", () => {
    expect(createCatalogueHref("zomato", "dineout")).toBe("/catalogues/new?platform=zomato&catalogue_type=dineout");
    expect(cataloguesHref({ type: "restaurant" })).toBe("/catalogues?type=restaurant");
  });
});
