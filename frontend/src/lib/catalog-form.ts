import type { CatalogueType, Platform } from "@/lib/catalog-types";
import { platformLabel } from "@/lib/catalog-types";

export function hostnameOf(value: string): string | null {
  try {
    const parsed = new URL(value.trim());
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return null;
    }
    return parsed.hostname.replace(/^www\./i, "").toLowerCase();
  } catch {
    return null;
  }
}

export function isSwiggyRestaurantUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim());
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return false;
    }
    const host = parsed.hostname.replace(/^www\./i, "").toLowerCase();
    if (host !== "swiggy.com") {
      return false;
    }
    const path = parsed.pathname;
    return /\/city\/[^/]+\/.+/i.test(path) || /rest\d+/i.test(path);
  } catch {
    return false;
  }
}

export function isSwiggyDineoutUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim());
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return false;
    }
    const host = parsed.hostname.replace(/^www\./i, "").toLowerCase();
    if (host !== "swiggy.com") {
      return false;
    }
    const path = parsed.pathname.toLowerCase();
    return path.includes("dineout") || path.includes("/restaurants/");
  } catch {
    return false;
  }
}

export function urlMatchesPlatform(platform: Platform, value: string): boolean {
  const host = hostnameOf(value);
  if (!host) {
    return false;
  }
  if (platform === "zomato") {
    return host === "zomato.com" || host.endsWith(".zomato.com");
  }
  if (platform === "magicpin") {
    return host === "magicpin.in" || host.endsWith(".magicpin.in");
  }
  return host === "swiggy.com" || host.endsWith(".swiggy.com");
}

export function platformUrlHint(platform: Platform): string {
  return `Enter a ${platformLabel(platform)} restaurant or Dineout URL.`;
}

export function platformUrlMismatchMessage(platform: Platform): string {
  return `This URL does not belong to the selected platform. Please enter a ${platformLabel(platform)} URL.`;
}

export type CatalogFormValues = {
  restaurant_name: string;
  fssai_number: string;
  swiggy_url: string;
};

export type CatalogFormErrors = Partial<
  Record<keyof CatalogFormValues | "dineout_url" | "catalogue_type" | "platform", string>
>;

export type CreateCatalogueValues = CatalogFormValues & {
  catalogue_type: CatalogueType;
  dineout_url?: string;
  platform?: Platform;
};

export function validateCatalogForm(values: CatalogFormValues): CatalogFormErrors {
  return validateCreateCatalogueForm({ ...values, catalogue_type: "restaurant", platform: "swiggy" });
}

export function validateCreateCatalogueForm(values: CreateCatalogueValues): CatalogFormErrors {
  const errors: CatalogFormErrors = {};
  const type = values.catalogue_type;
  const platform = values.platform || "swiggy";
  const label = platformLabel(platform);
  if (!values.restaurant_name.trim()) {
    errors.restaurant_name = type === "dineout" ? "Venue name is required." : "Restaurant name is required.";
  }
  if (type === "restaurant" || type === "both") {
    if (!values.fssai_number.trim()) {
      errors.fssai_number = "FSSAI license number is required.";
    }
  }
  if (!values.swiggy_url.trim()) {
    errors.swiggy_url = `${label} URL is required.`;
  } else if (!urlMatchesPlatform(platform, values.swiggy_url)) {
    errors.swiggy_url = platformUrlMismatchMessage(platform);
  } else if (platform === "swiggy") {
    if (type === "restaurant" || type === "both") {
      if (!isSwiggyRestaurantUrl(values.swiggy_url)) {
        errors.swiggy_url =
          "Enter a Swiggy restaurant URL, for example https://www.swiggy.com/city/city-name/restaurant-name-rest123.";
      }
    } else if (!isSwiggyDineoutUrl(values.swiggy_url) && !isSwiggyRestaurantUrl(values.swiggy_url)) {
      errors.swiggy_url = "Enter a Swiggy Dineout URL.";
    }
  }
  if (type === "both") {
    if (!values.dineout_url?.trim()) {
      errors.dineout_url = `${label} Dineout URL is required.`;
    } else if (!urlMatchesPlatform(platform, values.dineout_url)) {
      errors.dineout_url = platformUrlMismatchMessage(platform);
    } else if (
      platform === "swiggy" &&
      !isSwiggyDineoutUrl(values.dineout_url) &&
      !isSwiggyRestaurantUrl(values.dineout_url)
    ) {
      errors.dineout_url = "Enter a Swiggy Dineout URL.";
    }
  }
  return errors;
}

export function restaurantSlug(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "restaurant";
}
