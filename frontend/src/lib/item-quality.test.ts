import { describe, expect, it } from "vitest";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import { itemQualityRows } from "@/lib/item-quality";

const catalogue: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Brew 59",
  fssai_number: "1",
  source_url: "https://example.com",
  categories: [
    {
      name: "Drinks",
      items: [
        {
          name: "Fresh Lemonade",
          description: null,
          labels: [],
          image_url: "https://cdn.example/lemonade.jpg",
          price: 120,
        },
      ],
    },
  ],
};

describe("item quality rows", () => {
  it("exposes per-aspect letters for Fresh Lemonade", () => {
    const rows = itemQualityRows(catalogue, null);
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe("Fresh Lemonade");
    const byKey = Object.fromEntries(rows[0].aspects.map((aspect) => [aspect.key, aspect]));
    expect(byKey.description.letter).toBe("F");
    expect(byKey.description.status).toBe("Missing");
    expect(byKey.labels.letter).toBe("F");
    expect(byKey.image.letter).toBe("A");
    expect(byKey.price.letter).toBe("A");
    expect(byKey.description.canImprove).toBe(true);
  });
});
