import { describe, expect, it } from "vitest";
import {
  isSwiggyDineoutUrl,
  isSwiggyRestaurantUrl,
  platformUrlHint,
  platformUrlMismatchMessage,
  urlMatchesPlatform,
  validateCatalogForm,
  validateCreateCatalogueForm,
} from "@/lib/catalog-form";

describe("catalogue form validation", () => {
  it("accepts a Swiggy restaurant URL", () => {
    expect(
      isSwiggyRestaurantUrl(
        "https://www.swiggy.com/city/mangaluru/barbeque-nation-father-mullers-road-kankanady-rest302695",
      ),
    ).toBe(true);
  });

  it("rejects non-Swiggy URLs", () => {
    expect(isSwiggyRestaurantUrl("https://example.com/menu")).toBe(false);
    expect(isSwiggyRestaurantUrl("not-a-url")).toBe(false);
  });

  it("requires all create-catalogue fields", () => {
    const errors = validateCatalogForm({
      restaurant_name: "",
      fssai_number: "",
      swiggy_url: "https://zomato.com/x",
    });
    expect(errors.restaurant_name).toBeTruthy();
    expect(errors.fssai_number).toBeTruthy();
    expect(errors.swiggy_url).toBeTruthy();
  });

  it("does not require FSSAI for dineout creation", () => {
    const errors = validateCreateCatalogueForm({
      catalogue_type: "dineout",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "",
      swiggy_url: "https://www.swiggy.com/restaurants/daffys-indiranagar/dineout",
    });
    expect(errors).toEqual({});
  });

  it("requires restaurant and dineout URLs for both", () => {
    const errors = validateCreateCatalogueForm({
      catalogue_type: "both",
      restaurant_name: "Daffy's",
      fssai_number: "12345678901234",
      swiggy_url: "https://www.swiggy.com/city/bangalore/daffys-rest1",
      dineout_url: "",
    });
    expect(errors.dineout_url).toBeTruthy();
    expect(isSwiggyDineoutUrl("https://www.swiggy.com/restaurants/x/dineout")).toBe(true);
  });

  it("rejects a Swiggy URL when Zomato is selected", () => {
    const errors = validateCreateCatalogueForm({
      catalogue_type: "restaurant",
      platform: "zomato",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "12345678901234",
      swiggy_url: "https://www.swiggy.com/city/bangalore/daffys-rest1",
    });
    expect(errors.swiggy_url).toBe(platformUrlMismatchMessage("zomato"));
    expect(errors.swiggy_url).toContain("Please enter a Zomato URL.");
    expect(errors.swiggy_url).toContain("This URL does not belong to the selected platform.");
  });

  it("keeps platform selection strict and never infers a switch", () => {
    expect(urlMatchesPlatform("swiggy", "https://www.swiggy.com/city/bangalore/x-rest1")).toBe(true);
    expect(urlMatchesPlatform("swiggy", "https://www.zomato.com/bangalore/x")).toBe(false);
    expect(urlMatchesPlatform("swiggy", "https://magicpin.in/Bangalore/x/store/1")).toBe(false);
    expect(urlMatchesPlatform("zomato", "https://www.zomato.com/bangalore/x")).toBe(true);
    expect(urlMatchesPlatform("zomato", "https://www.swiggy.com/city/bangalore/x-rest1")).toBe(false);
    expect(urlMatchesPlatform("magicpin", "https://magicpin.in/Bangalore/x/store/1")).toBe(true);
    expect(urlMatchesPlatform("magicpin", "https://www.swiggy.com/city/bangalore/x-rest1")).toBe(false);

    const swiggyVsZomato = validateCreateCatalogueForm({
      catalogue_type: "restaurant",
      platform: "swiggy",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "12345678901234",
      swiggy_url: "https://www.zomato.com/bangalore/daffys",
    });
    expect(swiggyVsZomato.swiggy_url).toBe(
      "This URL does not belong to the selected platform. Please enter a Swiggy URL.",
    );

    const swiggyVsMagicpin = validateCreateCatalogueForm({
      catalogue_type: "restaurant",
      platform: "swiggy",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "12345678901234",
      swiggy_url: "https://magicpin.in/Bangalore/x/store/1",
    });
    expect(swiggyVsMagicpin.swiggy_url).toContain("Please enter a Swiggy URL.");

    const magicpinOk = validateCreateCatalogueForm({
      catalogue_type: "dineout",
      platform: "magicpin",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "",
      swiggy_url: "https://magicpin.in/Bangalore/Defence-Colony/Restaurant/Daffys/store/5642c9",
    });
    expect(magicpinOk.swiggy_url).toBeUndefined();
    expect(platformUrlHint("zomato")).toBe("Enter a Zomato restaurant or Dineout URL.");
  });
});
