import { describe, expect, it } from "vitest";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { GradeFinding } from "@/lib/grade-types";
import {
  checkTitle,
  findingSummary,
  formatMeasuredValue,
  humanFailureReason,
  resolveFindingProducts,
  resolvePathProduct,
} from "@/lib/grade-ui";

const catalogue: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Demo",
  fssai_number: "1",
  source_url: "https://example.com",
  categories: [
    {
      name: "Breakfast",
      item_count: 30,
      items: [
        { name: "Veg Grilled Sandwich", description: null, image_url: "https://cdn.example/sandwich.jpg" },
        { name: "Masala Dosa", description: "", image_url: "https://cdn.example/dosa.jpg" },
        { name: "Paneer Roll", description: "Fresh and tasty roll", image_url: "https://cdn.example/paneer.jpg" },
        { name: "Veg Roll", description: "Fresh and tasty roll", image_url: "https://cdn.example/veg.jpg" },
      ],
    },
  ],
};

function finding(checkId: string, paths: string[]): GradeFinding {
  return {
    finding_id: `nlp:${checkId}`,
    section: checkId.includes("image") ? "vision" : "nlp",
    check_id: checkId,
    severity: "ordinary",
    result: "fail",
    why: "technical why",
    evidence: {
      failed_criterion: checkId,
      affected_count: paths.length || 2,
      affected_field: "description",
      measured_value: 0.43,
      paths,
      details: {},
    },
    recommendation: {
      finding_id: `nlp:${checkId}`,
      priority: 1,
      action: "Add descriptions.",
      section: "nlp",
      check_id: checkId,
      severity: "ordinary",
    },
  };
}

describe("grade operator presentation", () => {
  it("uses human-readable titles instead of check ids", () => {
    expect(checkTitle("missing_description")).toBe("Missing descriptions");
    expect(checkTitle("description_coverage")).toBe("Description coverage");
    expect(checkTitle("repeated_description")).toBe("Duplicate descriptions");
    expect(checkTitle("image_low_quality")).toBe("Low-quality photos");
    expect(checkTitle("category_count_mismatch")).toBe("Category item counts");
    expect(checkTitle("empty_item_labels")).toBe("Missing labels");
  });

  it("formats coverage as a percentage", () => {
    expect(formatMeasuredValue(0.430769)).toBe("43%");
  });

  it("resolves menu paths onto real catalogue items", () => {
    const product = resolvePathProduct(catalogue, "menus[0].categories[0].items[0].description");
    expect(product?.name).toBe("Veg Grilled Sandwich");
    expect(product?.category).toBe("Breakfast");
    expect(product?.imageUrl).toContain("sandwich.jpg");
  });

  it("lists actual items for missing descriptions", () => {
    const products = resolveFindingProducts(
      finding("missing_description", [
        "menus[0].categories[0].items[0].description",
        "menus[0].categories[0].items[1].description",
      ]),
      catalogue,
    );
    expect(products.map((row) => row.name)).toEqual(["Veg Grilled Sandwich", "Masala Dosa"]);
    expect(findingSummary(finding("missing_description", []), products)).toBe("2 items have no description.");
  });

  it("lists actual items that share a description", () => {
    const products = resolveFindingProducts(
      finding("repeated_description", [
        "menus[0].categories[0].items[2].description",
        "menus[0].categories[0].items[3].description",
      ]),
      catalogue,
    );
    expect(products.map((row) => row.name)).toEqual(["Paneer Roll", "Veg Roll"]);
  });

  it("lists the actual item for a low-quality image", () => {
    const products = resolveFindingProducts(
      finding("image_low_quality", ["menus[0].categories[0].items[0].image_url"]),
      catalogue,
    );
    expect(products[0]?.name).toBe("Veg Grilled Sandwich");
    expect(products[0]?.imageUrl).toContain("sandwich.jpg");
  });

  it("explains unsafe generation without developer jargon", () => {
    const text = humanFailureReason("hallucinated ingredients");
    expect(text).toContain("Baba couldn't safely generate this description.");
    expect(text.toLowerCase()).not.toContain("hallucin");
  });
});
