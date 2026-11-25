import { describe, expect, it } from "vitest";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import {
  filterGradingRows,
  gradingRowFromCatalogue,
  gradingWorkspaceHref,
  parseGradingTab,
  venueThumbnail,
} from "@/lib/grading-ui";

const restaurant: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "The Lassi Pub",
  fssai_number: "1",
  source_url: "https://www.swiggy.com/city/bangalore/the-lassi-pub-rest1",
  platform: "swiggy",
  catalogue_type: "restaurant",
  restaurant: { name: "The Lassi Pub", outlet: "Indiranagar, Bangalore", image_url: "https://cdn.example/lassi.jpg" },
};

const dineout: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Cochin Village",
  fssai_number: "1",
  source_url: "https://www.zomato.com/bangalore/cochin-village",
  platform: "zomato",
  catalogue_type: "dineout",
  dineout: {
    venue: "Cochin Village",
    hero_image: "https://cdn.example/cochin.jpg",
    location: { locality: "Koramangala" },
  },
};

describe("grading list helpers", () => {
  it("builds restaurant and dineout rows from stored catalogues without inventing a grade", () => {
    const graded = gradingRowFromCatalogue("cat_1", restaurant, "B", 78);
    const pending = gradingRowFromCatalogue("cat_2", dineout, null, null);
    expect(graded).toMatchObject({
      id: "cat_1",
      name: "The Lassi Pub",
      typeLabel: "Restaurant",
      platformLabel: "Swiggy",
      letter: "B",
      score: 78,
    });
    expect(pending.letter).toBeNull();
    expect(pending.name).toBe("Cochin Village");
    expect(venueThumbnail(restaurant)).toBe("https://cdn.example/lassi.jpg");
    expect(venueThumbnail(dineout)).toBe("https://cdn.example/cochin.jpg");
  });

  it("filters the owner list by domain and overall letter", () => {
    const rows = [
      gradingRowFromCatalogue("cat_1", restaurant, "B", 78),
      gradingRowFromCatalogue("cat_2", dineout, "F", 20),
      gradingRowFromCatalogue("cat_3", restaurant, null, null),
    ];
    expect(filterGradingRows(rows, "restaurant", "all").map((row) => row.id)).toEqual(["cat_1", "cat_3"]);
    expect(filterGradingRows(rows, "all", "F").map((row) => row.id)).toEqual(["cat_2"]);
    expect(filterGradingRows(rows, "all", "ungraded").map((row) => row.id)).toEqual(["cat_3"]);
  });

  it("keeps quality as the default workspace tab", () => {
    expect(gradingWorkspaceHref("cat_1")).toBe("/grading/cat_1");
    expect(gradingWorkspaceHref("cat_1", "photos")).toBe("/grading/cat_1?tab=photos");
    expect(parseGradingTab("video")).toBe("video");
    expect(parseGradingTab("unknown")).toBe("quality");
  });
});
