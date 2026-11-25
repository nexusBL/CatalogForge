import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ALL_CATEGORIES,
  FOOD_FILTER_ALL,
  FOOD_FILTER_NONVEG,
  FOOD_FILTER_VEG,
  categoryAnchor,
  customizationGroups,
  filterCatalogue,
  findItemByKey,
  formatPrice,
  formatStoredAddonPrice,
  hasProductImage,
  identifyCatalogue,
  isCustomizable,
  isVeg,
  matchesFoodFilter,
  matchesQuery,
  variantGroups,
} from "@/lib/catalogue-menu";
import type { CatalogueCategory, CatalogueItem } from "@/lib/catalog-types";

const chicken: CatalogueItem = {
  name: "Chicken Tikka",
  description: "Spiced chicken",
  price: 249,
  food_type: "NONVEG",
  additional_information: { id: "nv-1" },
};

const pizza: CatalogueItem = {
  name: "Margherita",
  description: "Cheese pizza",
  price: 149,
  original_price: 199,
  food_type: "VEG",
  labels: ["Bestseller"],
  variants: [{ group_name: "Crust", variations: [{ name: "Pan" }] }],
  customizations: [{ group_name: "Extra Cheese", choices: [{ name: "Cheese", price: 6500 }] }],
  additional_information: { id: "veg-1" },
};

const mystery: CatalogueItem = {
  name: "Chef Special",
  price: 199,
};

const categories: CatalogueCategory[] = [
  { name: "Pizza", items: [pizza] },
  { name: "Grill", items: [chicken] },
  { name: "Specials", items: [mystery] },
];

describe("catalogue menu helpers", () => {
  it("filters items by search across name, description, and category", () => {
    const byName = filterCatalogue(categories, "chicken");
    expect(byName).toHaveLength(1);
    expect(byName[0].items[0].name).toBe("Chicken Tikka");

    const byCategory = filterCatalogue(categories, "pizza");
    expect(byCategory.map((category) => category.name)).toEqual(["Pizza"]);

    expect(matchesQuery(pizza, "Pizza", "cheese")).toBe(true);
  });

  it("filters by a unique category key from stored source order", () => {
    const identified = identifyCatalogue(categories);
    const onlyGrill = filterCatalogue(identified, "", identified[1].key);
    expect(onlyGrill).toHaveLength(1);
    expect(onlyGrill[0].name).toBe("Grill");
    expect(filterCatalogue(identified, "", ALL_CATEGORIES)).toHaveLength(3);
  });

  it("keeps duplicate category names as distinct source sections", () => {
    const duplicate: CatalogueCategory[] = [
      { name: "Serves 1-2", items: [{ name: "Box A", food_type: "VEG", additional_information: { id: "a" } }] },
      { name: "Serves 1-2", items: [{ name: "Box B", food_type: "NONVEG", additional_information: { id: "b" } }] },
    ];
    const identified = identifyCatalogue(duplicate);
    expect(identified[0].key).not.toBe(identified[1].key);
    expect(identified.map((category) => category.name)).toEqual(["Serves 1-2", "Serves 1-2"]);
    const firstOnly = filterCatalogue(identified, "", identified[0].key);
    expect(firstOnly[0].items[0].name).toBe("Box A");
    expect(firstOnly[0].items.map((item) => item.name)).not.toContain("Box B");
  });

  it("assigns stable item keys from source ids", () => {
    const identified = identifyCatalogue(categories);
    expect(identified[0].items[0].key).toBe("item-veg-1");
    expect(findItemByKey(identified, "item-nv-1")?.name).toBe("Chicken Tikka");
  });

  it("prefers canonical item_id over source item id for keys", () => {
    const identified = identifyCatalogue([
      { name: "Mains", items: [{ name: "Rice", item_id: "uuid-1", additional_information: { id: "src-9" } }] },
    ]);
    expect(identified[0].items[0].key).toBe("item-uuid-1");
  });

  it("disambiguates duplicate source item ids across sections", () => {
    const duplicateIds: CatalogueCategory[] = [
      { name: "Recommended", items: [{ name: "Shared", additional_information: { id: "same" } }] },
      { name: "Starters", items: [{ name: "Shared again", additional_information: { id: "same" } }] },
    ];
    const identified = identifyCatalogue(duplicateIds);
    expect(identified[0].items[0].key).toBe("item-same");
    expect(identified[1].items[0].key).toBe("item-same-1-0");
    expect(findItemByKey(identified, "item-same-1-0")?.name).toBe("Shared again");
  });

  it("filters vegetarian and non-vegetarian items from stored food_type", () => {
    const all = filterCatalogue(categories, "", ALL_CATEGORIES, FOOD_FILTER_ALL);
    expect(all.flatMap((category) => category.items).map((item) => item.name)).toEqual([
      "Margherita",
      "Chicken Tikka",
      "Chef Special",
    ]);

    const veg = filterCatalogue(categories, "", ALL_CATEGORIES, FOOD_FILTER_VEG);
    expect(veg.flatMap((category) => category.items).map((item) => item.name)).toEqual(["Margherita"]);

    const nonveg = filterCatalogue(categories, "", ALL_CATEGORIES, FOOD_FILTER_NONVEG);
    expect(nonveg.flatMap((category) => category.items).map((item) => item.name)).toEqual(["Chicken Tikka"]);
  });

  it("does not classify unknown food_type as veg or non-veg", () => {
    expect(isVeg(undefined)).toBeNull();
    expect(matchesFoodFilter(mystery, FOOD_FILTER_VEG)).toBe(false);
    expect(matchesFoodFilter(mystery, FOOD_FILTER_NONVEG)).toBe(false);
    expect(matchesFoodFilter(mystery, FOOD_FILTER_ALL)).toBe(true);
  });

  it("combines search with veg and non-veg filters", () => {
    const vegSearch = filterCatalogue(categories, "chicken", ALL_CATEGORIES, FOOD_FILTER_VEG);
    expect(vegSearch).toHaveLength(0);
    const nonvegSearch = filterCatalogue(categories, "chicken", ALL_CATEGORIES, FOOD_FILTER_NONVEG);
    expect(nonvegSearch[0].items[0].name).toBe("Chicken Tikka");
  });

  it("formats stored prices without inventing missing ones", () => {
    expect(formatPrice(399)).toBe("₹399");
    expect(formatPrice(null)).toBeNull();
    expect(formatPrice("")).toBeNull();
    expect(formatStoredAddonPrice(6500)).toBe("₹65");
  });

  it("parses variant and customization groups from stored objects", () => {
    expect(isCustomizable(pizza)).toBe(true);
    expect(isVeg("VEG")).toBe(true);
    expect(isVeg("NONVEG")).toBe(false);
    expect(variantGroups(pizza)[0].options.map((option) => option.name)).toEqual(["Pan"]);
    expect(customizationGroups(pizza)[0].options[0]).toEqual({ name: "Cheese", price: "₹65", amount: 65, id: "Cheese" });
    expect(categoryAnchor("Recommended", 0)).toBe("category-0-recommended");
  });

  it("keeps Barbeque Nation source sections and unique keys", () => {
    const payloadPath = resolve(
      process.cwd(),
      "..",
      "output",
      "swiggy",
      "barbeque-nation-father-mullers-road-kankanady-rest302695.json",
    );
    expect(existsSync(payloadPath)).toBe(true);
    const payload = JSON.parse(readFileSync(payloadPath, "utf8")) as {
      item_count?: number;
      image_count?: number;
      categories: CatalogueCategory[];
    };
    expect(payload.categories).toHaveLength(17);
    expect(payload.item_count).toBe(77);
    expect(payload.image_count).toBe(78);
    expect(payload.categories.map((category) => category.name).filter((name) => name === "Serves 1-2")).toHaveLength(2);
    const identified = identifyCatalogue(payload.categories);
    const categoryKeys = identified.map((category) => category.key);
    const itemKeys = identified.flatMap((category) => category.items.map((item) => item.key));
    expect(new Set(categoryKeys).size).toBe(17);
    expect(itemKeys).toHaveLength(77);
    expect(new Set(itemKeys).size).toBe(77);
    expect(filterCatalogue(payload.categories, "", ALL_CATEGORIES, FOOD_FILTER_VEG).flatMap((category) => category.items)).toHaveLength(37);
    expect(filterCatalogue(payload.categories, "", ALL_CATEGORIES, FOOD_FILTER_NONVEG).flatMap((category) => category.items)).toHaveLength(40);
  });

  it("keeps a selected category visible even when it has no matching items", () => {
    const identified = identifyCatalogue([
      { name: "Desserts", items: [] },
      { name: "Starters", items: [chicken] },
    ]);
    const onlyDesserts = filterCatalogue(identified, "", identified[0].key);
    expect(onlyDesserts.map((category) => category.name)).toEqual(["Desserts"]);
    expect(onlyDesserts[0].items).toHaveLength(0);
  });

  it("treats materialized catalogue assets as product images and rejects veg icons", () => {
    expect(hasProductImage({ name: "Lassi", image_url: "/catalogue-assets/abc/dish.img" })).toBe(true);
    expect(hasProductImage({ name: "Lassi", image_url: "https://cdn.example/lassi.jpg" })).toBe(true);
    expect(hasProductImage({ name: "Lassi", image_url: "https://magicpin.in/images/merchant/veg-icon.svg" })).toBe(false);
    expect(hasProductImage({ name: "Lassi" })).toBe(false);
  });

  it("composes bestseller and image filters with food type", () => {
    const pictured = {
      name: "Pictured Veg",
      food_type: "VEG",
      image_url: "https://cdn.example/a.jpg",
      labels: ["Bestseller"],
    };
    const data: CatalogueCategory[] = [
      { name: "Mix", items: [pictured, { name: "No Photo", food_type: "VEG" }, chicken] },
    ];
    const bestseller = filterCatalogue(data, "", ALL_CATEGORIES, FOOD_FILTER_VEG, "with", true);
    expect(bestseller.flatMap((category) => category.items).map((item) => item.name)).toEqual(["Pictured Veg"]);
  });
});
