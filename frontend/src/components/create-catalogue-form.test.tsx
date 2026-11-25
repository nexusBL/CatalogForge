import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  CatalogueBlockedState,
  CatalogueCreateProgress,
  CatalogueCreatedSummary,
  CatalogueTypePicker,
  CreateModePicker,
} from "@/components/create-catalogue-form";
import { platformUrlHint } from "@/lib/catalog-form";
import type { CatalogCreateResponse } from "@/lib/catalog-types";

const success: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Harbor Spice House",
  fssai_number: "12345678901234",
  source_url: "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
  restaurant: { name: "Harbor Spice House" },
  categories: [{ name: "Breads", items: [{ name: "Butter Naan" }] }],
  item_count: 12,
  image_count: 13,
  id: "cat_123",
};

describe("create catalogue UI", () => {
  it("shows progress bar while creating", () => {
    const html = renderToStaticMarkup(<CatalogueCreateProgress currentStep={2} />);
    expect(html).toContain("Creating your catalogue...");
    expect(html).toContain("38%");
    expect(html).toContain('role="status"');
  });

  it("renders successful catalogue counts from the API", () => {
    const html = renderToStaticMarkup(<CatalogueCreatedSummary catalogue={success} />);
    expect(html).toContain("Catalogue Created");
    expect(html).toContain("Harbor Spice House");
    expect(html).toContain("Categories: 1");
    expect(html).toContain("Items: 12");
    expect(html).toContain("Images: 13");
    expect(html).toContain("/catalogues/cat_123");
  });

  it("renders a blocked state without menu items", () => {
    const html = renderToStaticMarkup(<CatalogueBlockedState onRetry={() => undefined} />);
    expect(html).toContain("Swiggy could not be accessed right now.");
    expect(html).toContain("Retry");
    expect(html).toContain("Back");
    expect(html).not.toContain("Butter Naan");
  });

  it("uses the selected platform in blocked copy", () => {
    const zomato = renderToStaticMarkup(
      <CatalogueBlockedState onRetry={() => undefined} platform="zomato" />,
    );
    const magicpin = renderToStaticMarkup(
      <CatalogueBlockedState onRetry={() => undefined} platform="magicpin" />,
    );
    expect(zomato).toContain("Zomato could not be accessed right now.");
    expect(magicpin).toContain("Magicpin could not be accessed right now.");
  });

  it("lets the user choose single venue or area discovery", () => {
    const html = renderToStaticMarkup(<CreateModePicker onSelect={() => undefined} />);
    expect(html).toContain("Single Venue");
    expect(html).toContain("Area / City");
    expect(html).not.toContain("FSSAI License Number");
  });

  it("asks the user to choose Restaurant, Dineout, or Both first", () => {
    const html = renderToStaticMarkup(<CatalogueTypePicker onSelect={() => undefined} />);
    expect(html).toContain("What would you like to create?");
    expect(html).toContain("Restaurant");
    expect(html).toContain("Dineout");
    expect(html).toContain("Both");
    expect(html).not.toContain("FSSAI License Number");
  });

  it("shows a platform URL helper", () => {
    expect(platformUrlHint("swiggy")).toBe("Enter a Swiggy restaurant or Dineout URL.");
    expect(platformUrlHint("magicpin")).toBe("Enter a Magicpin restaurant or Dineout URL.");
  });
});
