import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CatalogueImage } from "@/components/catalogue-image";
import { CatalogueLoading, CatalogueView } from "@/components/catalogue-view";
import type { CatalogCreateResponse } from "@/lib/catalog-types";

const success: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Harbor Spice House",
  fssai_number: "12345678901234",
  source_url: "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
  restaurant: {
    name: "Harbor Spice House",
    rating: 4.4,
    cuisines: ["Coastal"],
    price_for_two: "₹1200 for two",
    outlet: "Sample Road",
    address: "1 Sample Road",
    image_url: "https://cdn.example/restaurant.jpg",
  },
  categories: [
    {
      name: "Breads",
      items: [
        {
          name: "Butter Naan",
          description: "Tandoor baked",
          price: 70,
          food_type: "VEG",
          labels: ["Bestseller"],
          image_url: "https://cdn.example/naan.jpg",
          variants: [{ group_name: "Size", variations: [{ name: "Regular" }] }],
          customizations: [{ group_name: "Add ons", choices: [{ name: "Butter" }] }],
          additional_information: { id: "naan-1" },
        },
      ],
    },
    {
      name: "Grill",
      items: [
        {
          name: "Chicken Tikka",
          description: "Charred chicken",
          price: 249,
          food_type: "NONVEG",
          image_url: "https://cdn.example/tikka.jpg",
          additional_information: { id: "tikka-1" },
        },
        {
          name: "Chicken Tikka",
          description: "Second tikka",
          price: 299,
          food_type: "NONVEG",
          additional_information: { id: "tikka-2" },
        },
      ],
    },
    {
      name: "Serves 1-2",
      items: [{ name: "Box A", food_type: "VEG", additional_information: { id: "box-a" } }],
    },
    {
      name: "Serves 1-2",
      items: [{ name: "Box B", food_type: "NONVEG", additional_information: { id: "box-b" } }],
    },
    {
      name: "Specials",
      items: [{ name: "Chef Special", price: 199 }],
    },
  ],
  item_count: 6,
  image_count: 3,
};

describe("catalogue rendering", () => {
  it("renders dynamic categories and items from stored catalogue data", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} />);
    expect(html).toContain("Harbor Spice House");
    expect(html).toContain("Breads");
    expect(html).toContain("Grill");
    expect(html).toContain("Butter Naan");
    expect(html).toContain("Chicken Tikka");
    expect(html).toContain("Best Seller");
    expect(html).toContain("₹70");
    expect(html).toContain("https://cdn.example/naan.jpg");
    expect(html).toContain("Categories: 5");
    expect(html).toContain("Items: 6");
    expect(html).toContain("tablet:grid-cols-2");
    expect(html).toContain("laptop:grid-cols-3");
    expect(html).toContain("desktop:grid-cols-4");
    expect(html).toContain("bg-card");
    expect(html).toContain("text-card-foreground");
    expect(html.indexOf("Butter Naan")).toBeLessThan(html.indexOf("About Restaurant"));
    expect(html.indexOf("Search the menu")).toBeLessThan(html.indexOf("About Restaurant"));
    expect(html).toContain("FSSAI License");
  });

  it("filters to a stored category without hard-coded menu names", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} initialCategory="Grill" />);
    expect(html).toContain("Chicken Tikka");
    expect(html).not.toContain("Butter Naan");
  });

  it("shows items for a later category instead of an empty panel", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          categories: [
            ...(success.categories || []),
            { name: "Desserts", items: [{ name: "Gulab Jamun", price: 49, food_type: "VEG" }] },
            { name: "Beverages", items: [{ name: "Sweet Lassi", price: 73, food_type: "VEG" }] },
          ],
          item_count: 8,
        }}
        initialCategory="Beverages"
      />,
    );
    expect(html).toContain("Sweet Lassi");
    expect(html).not.toContain("Butter Naan");
    expect(html).not.toContain("No items match your search.");
  });

  it("searches stored item names and descriptions", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} initialQuery="chicken" />);
    expect(html).toContain("Chicken Tikka");
    expect(html).not.toContain("Butter Naan");
  });

  it("hides missing fields instead of empty placeholders", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          restaurant: { name: "Harbor Spice House" },
          categories: [{ name: "Breads", items: [{ name: "Plain Rice", price: 80 }] }],
          item_count: 1,
        }}
      />,
    );
    expect(html).toContain("Plain Rice");
    expect(html).toContain("₹80");
    expect(html).not.toContain("line-through");
    expect(html).not.toContain("Tandoor baked");
    expect(html).not.toContain("Customisable");
  });

  it("opens an item detail view with variants and customizations", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} openItemName="Butter Naan" />);
    expect(html).toContain("item-detail-title");
    expect(html).toContain("Variants");
    expect(html).toContain("Size");
    expect(html).toContain("Customizations");
    expect(html).toContain("Add ons");
    expect(html).toContain("Tandoor baked");
  });

  it("shows a fallback when an image URL is missing", () => {
    const html = renderToStaticMarkup(<CatalogueImage alt="Missing" />);
    expect(html).toContain("catalogue-image-fallback");
    expect(html).not.toContain("<img");
  });

  it("lazy-loads real image URLs", () => {
    const html = renderToStaticMarkup(
      <CatalogueImage src="https://cdn.example/naan.jpg" alt="Butter Naan" className="object-cover" />,
    );
    expect(html).toContain("https://cdn.example/naan.jpg");
    expect(html).toContain('loading="lazy"');
    expect(html).not.toContain("catalogue-image-fallback");
  });

  it("shows an empty catalogue message without fabricating items", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          categories: [],
          item_count: 0,
          restaurant: { name: "Harbor Spice House" },
        }}
      />,
    );
    expect(html).toContain("No menu items were available in this catalogue.");
    expect(html).not.toContain("Butter Naan");
  });

  it("renders a loading state", () => {
    const html = renderToStaticMarkup(<CatalogueLoading />);
    expect(html).toContain("Loading catalogue…");
  });

  it("shows a blocked extraction error instead of menu data", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          extraction_status: "blocked",
          restaurant: null,
          categories: [],
          error: "Swiggy/CloudFront denied the restaurant page (HTTP 403).",
        }}
      />,
    );
    expect(html).toContain("Swiggy could not be accessed right now.");
    expect(html).toContain("HTTP 403");
    expect(html).not.toContain("Butter Naan");
  });

  it("shows Zomato blocked copy from the stored platform", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          platform: "zomato",
          source_url: "https://www.zomato.com/bangalore/daffys-brewgarden-indiranagar-bangalore",
          extraction_status: "blocked",
          restaurant: null,
          categories: [],
          error: "denied",
        }}
      />,
    );
    expect(html).toContain("Zomato could not be accessed right now.");
  });

  it("uses theme tokens that work in light and dark mode", () => {
    const html = renderToStaticMarkup(
      <div className="dark bg-background text-foreground">
        <CatalogueView catalogue={success} />
      </div>,
    );
    expect(html).toContain("dark");
    expect(html).toContain("bg-background");
    expect(html).toContain("bg-card");
    expect(html).toContain("text-muted-foreground");
    expect(html).toContain("border-border");
    expect(html).toContain("from-black/80");
    expect(html).not.toContain("from-background/95");
  });

  it("uses a right drawer for details/cart and a bottom-right cart balloon after items are added", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} />);
    expect(html).toContain("View details");
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "catalogue-view.tsx"), "utf8");
    expect(source).toContain("fixed bottom-6 right-6");
    expect(source).toContain("rounded-full");
    expect(source).toContain("cart.length > 0 && !cartOpen");
    expect(source).not.toContain("fixed right-4 top-4");
    expect(source).not.toContain("fixed inset-0 z-[90]");
    expect(source).toContain('aria-label="Cart"');
    expect(source).toContain("justify-end");
    expect(source).toContain("Product Details");
    expect(source).toContain("Customizations");
    expect(source).not.toContain("YOUR CART");
  });

  it("renders duplicate category and item names with unique source keys", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} />);
    expect(html).toContain('data-category-key="category-2"');
    expect(html).toContain('data-category-key="category-3"');
    expect(html).toContain("Box A");
    expect(html).toContain("Box B");
    expect(html).toContain('data-item-key="item-tikka-1"');
    expect(html).toContain('data-item-key="item-tikka-2"');
    expect(html.match(/Serves 1-2/g)?.length).toBeGreaterThan(1);
  });

  it("shows all items by default including unknown food types", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} initialFoodFilter="all" />);
    expect(html).toContain("Butter Naan");
    expect(html).toContain("Chicken Tikka");
    expect(html).toContain("Chef Special");
    expect(html).toContain("Vegetarian");
    expect(html).toContain("Non-vegetarian");
  });

  it("filters to vegetarian items from stored food_type", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} initialFoodFilter="veg" />);
    expect(html).toContain("Butter Naan");
    expect(html).toContain("Box A");
    expect(html).not.toContain("Chicken Tikka");
    expect(html).not.toContain("Chef Special");
  });

  it("filters to non-vegetarian items from stored food_type", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} initialFoodFilter="nonveg" />);
    expect(html).toContain("Chicken Tikka");
    expect(html).toContain("Box B");
    expect(html).not.toContain("Butter Naan");
    expect(html).not.toContain("Chef Special");
  });

  it("does not invent a veg indicator for unknown food_type", () => {
    const html = renderToStaticMarkup(
      <CatalogueView catalogue={success} initialCategory="Specials" />,
    );
    expect(html).toContain("Chef Special");
    expect(html).not.toContain('title="Vegetarian"');
    expect(html).not.toContain('title="Non-vegetarian"');
  });

  it("applies search with the veg filter", () => {
    const html = renderToStaticMarkup(
      <CatalogueView catalogue={success} initialQuery="chicken" initialFoodFilter="veg" />,
    );
    expect(html).not.toContain("Chicken Tikka");
    expect(html).not.toContain("Butter Naan");
  });

  it("applies search with the non-veg filter", () => {
    const html = renderToStaticMarkup(
      <CatalogueView catalogue={success} initialQuery="chicken" initialFoodFilter="nonveg" />,
    );
    expect(html).toContain("Chicken Tikka");
    expect(html).not.toContain("Butter Naan");
  });

  it("opens view details for the selected source item", () => {
    const html = renderToStaticMarkup(
      <CatalogueView catalogue={success} openItemKey="item-tikka-2" />,
    );
    expect(html).toContain('data-item-key="item-tikka-2"');
    expect(html).toContain("Second tikka");
    expect(html).toContain("item-detail-title");
  });

  it("keeps view details working after veg filtering", () => {
    const html = renderToStaticMarkup(
      <CatalogueView catalogue={success} initialFoodFilter="veg" openItemKey="item-naan-1" />,
    );
    expect(html).toContain("Tandoor baked");
    expect(html).toContain('data-item-key="item-naan-1"');
  });

  it("keeps view details working after category switching", () => {
    const html = renderToStaticMarkup(
      <CatalogueView catalogue={success} initialCategory="category-3" openItemKey="item-box-b" />,
    );
    expect(html).toContain("Box B");
    expect(html).toContain('data-item-key="item-box-b"');
    expect(html).not.toContain("Box A");
  });

  it("closes details when no item is selected and can reopen another item", () => {
    const closed = renderToStaticMarkup(<CatalogueView catalogue={success} />);
    expect(closed).not.toContain("item-detail-title");
    const reopened = renderToStaticMarkup(
      <CatalogueView catalogue={success} openItemKey="item-naan-1" />,
    );
    expect(reopened).toContain("item-detail-title");
    expect(reopened).toContain("Butter Naan");
  });

  it("opens product details in a right-side drawer", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} openItemKey="item-naan-1" />);
    expect(html).toContain("Product Details");
    expect(html).toContain("justify-end");
    expect(html).toContain("Cart");
    expect(html).toContain("Add to Cart");
    expect(html).toContain("slide-in-from-right");
  });

  it("filters best sellers from stored source labels", () => {
    const html = renderToStaticMarkup(<CatalogueView catalogue={success} initialBestseller />);
    expect(html).toContain("Butter Naan");
    expect(html).not.toContain("Chicken Tikka");
  });

  it("filters items with and without images", () => {
    const withImages = renderToStaticMarkup(<CatalogueView catalogue={success} initialImageFilter="with" />);
    expect(withImages).toContain("Butter Naan");
    expect(withImages).not.toContain("Chef Special");
    const withoutImages = renderToStaticMarkup(<CatalogueView catalogue={success} initialImageFilter="without" />);
    expect(withoutImages).toContain("Chef Special");
    expect(withoutImages).not.toContain("Butter Naan");
  });

  it("combines search, veg, bestseller, and image filters", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={success}
        initialQuery="naan"
        initialFoodFilter="veg"
        initialBestseller
        initialImageFilter="with"
      />,
    );
    expect(html).toContain("Butter Naan");
    expect(html).not.toContain("Chicken Tikka");
  });

  it("keeps unavailable items visible with next-available text", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          categories: [
            {
              name: "Late Night",
              items: [
                {
                  name: "4 Course Meal",
                  price: 289,
                  food_type: "VEG",
                  available: false,
                  next_available: "11 pm, today",
                  additional_information: { id: "late-1", inStock: 0 },
                },
              ],
            },
          ],
          item_count: 1,
        }}
      />,
    );
    expect(html).toContain("4 Course Meal");
    expect(html).toContain("Next available at 11 pm, today");
  });

  it("renders Edit Hero with AI action targeting restaurant.image_url", () => {
    const html = renderToStaticMarkup(
      <CatalogueView
        catalogue={{
          ...success,
          id: "cat_test_hero_ux",
        }}
      />,
    );
    expect(html).toContain("Edit Hero with AI");
    expect(html).toContain('href="/catalogues/cat_test_hero_ux/media?path=restaurant.image_url"');
  });
});
