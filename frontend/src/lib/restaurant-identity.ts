import type {
  CatalogueRestaurant,
  CatalogueType,
  CatalogCreateResponse,
  DineoutVenue,
  StoredCatalogue,
} from "@/lib/catalog-types";
import { cataloguePlatform } from "@/lib/catalog-types";

export function catalogueType(value: string | null | undefined): CatalogueType {
  if (value === "dineout" || value === "both") {
    return value;
  }
  return "restaurant";
}

export function catalogueTypeLabel(value: string | null | undefined): string {
  const type = catalogueType(value);
  if (type === "dineout") {
    return "Dineout";
  }
  if (type === "both") {
    return "Both";
  }
  return "Restaurant";
}

export function isDistanceText(value: string | null | undefined): boolean {
  const text = (value || "").trim();
  if (!text) {
    return false;
  }
  return /^\d+(?:\.\d+)?\s*(?:km|kms|kilometers?|m|meters?)(?:\s+away)?$/i.test(text);
}

function urlHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return "";
  }
}

export function platformUrlSlots(
  sourceUrl?: string | null,
  restaurant?: CatalogueRestaurant | null,
): { swiggy: string | null; zomato: string | null; magicpin: string | null; district: string | null } {
  const slots = { swiggy: null as string | null, zomato: null as string | null, magicpin: null as string | null, district: null as string | null };
  const assign = (url: string | null | undefined) => {
    const text = presentText(url);
    if (!text) {
      return;
    }
    const host = urlHost(text);
    if (host === "district.in" || host.endsWith(".district.in")) {
      slots.district = text;
      return;
    }
    if (host === "swiggy.com" || host.endsWith(".swiggy.com")) {
      slots.swiggy = text;
      return;
    }
    if (host === "zomato.com" || host.endsWith(".zomato.com")) {
      slots.zomato = text;
      return;
    }
    if (host === "magicpin.in" || host.endsWith(".magicpin.in")) {
      slots.magicpin = text;
    }
  };
  assign(sourceUrl);
  assign(restaurant?.zomato_url);
  assign(restaurant?.magicpin_url);
  return slots;
}

export function restaurantLocation(restaurant: CatalogueRestaurant | null | undefined): string | null {
  const outlet = restaurant?.outlet?.trim();
  if (outlet && !isDistanceText(outlet)) {
    return outlet;
  }
  const address = restaurant?.address?.trim();
  if (address && !isDistanceText(address)) {
    return address;
  }
  return null;
}

export function restaurantDisplayName(
  restaurant: CatalogueRestaurant | null | undefined,
  fallback?: string | null,
): string {
  return restaurant?.name?.trim() || (fallback || "").trim() || "Restaurant";
}

export function venueDisplayName(result: CatalogCreateResponse): string {
  const type = catalogueType(result.catalogue_type);
  if (type === "dineout") {
    return presentText(result.dineout?.venue) || restaurantDisplayName(result.restaurant, result.restaurant_name);
  }
  return restaurantDisplayName(result.restaurant, result.restaurant_name);
}

export function venueLocation(result: CatalogCreateResponse): string | null {
  const dineoutLocation =
    presentText(result.dineout?.location?.outlet) ||
    presentText(result.dineout?.location?.locality) ||
    presentText(result.dineout?.location?.address);
  if (catalogueType(result.catalogue_type) === "dineout") {
    return dineoutLocation || restaurantLocation(result.restaurant);
  }
  return restaurantLocation(result.restaurant) || dineoutLocation;
}

export function outletIdentity(name: string, location: string | null | undefined): string {
  return [name.trim(), (location || "").trim()].filter(Boolean).join(" · ");
}

export function presentText(value: unknown): string | null {
  if (value == null) {
    return null;
  }
  const text = String(value).trim();
  if (!text || text === "null" || text === "undefined" || text.toLowerCase() === "n/a" || text.toLowerCase() === "not available") {
    return null;
  }
  return text;
}

export function plausibleVenueDistance(value: unknown): string | null {
  const text = presentText(value);
  if (!text) {
    return null;
  }
  const match = text.match(/([\d.]+)\s*(km|m)\b/i);
  if (!match) {
    return null;
  }
  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return null;
  }
  const kilometres = match[2].toLowerCase() === "m" ? amount / 1000 : amount;
  if (kilometres > 20) {
    return null;
  }
  return text;
}

export function looksLikeUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

export type AboutField = {
  label: string;
  value: string;
  href?: string;
  kind?: "location" | "license" | "rating" | "link" | "restaurant" | "phone";
};

export function restaurantAboutFields(input: {
  restaurant?: CatalogueRestaurant | null;
  restaurantName?: string;
  fssaiNumber?: string;
  sourceUrl?: string;
}): AboutField[] {
  const restaurant = input.restaurant;
  const fields: AboutField[] = [];
  const name = restaurantDisplayName(restaurant, input.restaurantName || "");
  if (name && name !== "Restaurant") {
    fields.push({ label: "Restaurant Name", value: name, kind: "restaurant" });
  }
  const location = presentText(restaurant?.outlet);
  const address = presentText(restaurant?.address);
  if (address && address !== location && !isDistanceText(address)) {
    fields.push({ label: "Address", value: address, kind: "location" });
  }
  const fssai = presentText(restaurant?.fssai_license) || presentText(input.fssaiNumber);
  if (fssai) {
    fields.push({ label: "FSSAI License", value: fssai, kind: "license" });
  }
  if (restaurant?.rating != null) {
    const count = presentText(restaurant.rating_count);
    fields.push({
      label: "Swiggy Rating",
      value: count ? `${restaurant.rating} (${count})` : String(restaurant.rating),
      kind: "rating",
    });
  }
  const urls = platformUrlSlots(input.sourceUrl, restaurant);
  if (urls.swiggy) {
    fields.push({ label: "Swiggy URL", value: urls.swiggy, href: urls.swiggy, kind: "link" });
  }
  if (restaurant?.zomato_rating != null) {
    fields.push({ label: "Zomato Rating", value: String(restaurant.zomato_rating), kind: "rating" });
  }
  if (urls.zomato) {
    fields.push({ label: "Zomato URL", value: urls.zomato, href: urls.zomato, kind: "link" });
  }
  if (restaurant?.magicpin_rating != null) {
    fields.push({ label: "Magicpin Rating", value: String(restaurant.magicpin_rating), kind: "rating" });
  }
  if (urls.magicpin) {
    fields.push({ label: "Magicpin URL", value: urls.magicpin, href: urls.magicpin, kind: "link" });
  }
  if (urls.district) {
    fields.push({ label: "District URL", value: urls.district, href: urls.district, kind: "link" });
  }
  return fields;
}

export function dineoutAboutFields(venue: DineoutVenue | null | undefined, fallbackUrl?: string): AboutField[] {
  if (!venue) {
    return [];
  }
  const fields: AboutField[] = [];
  const name = presentText(venue.venue);
  if (name) {
    fields.push({ label: "Restaurant name", value: name, kind: "restaurant" });
  }
  const restaurantId = presentText(venue.restaurant_id);
  if (restaurantId) {
    fields.push({ label: "Restaurant ID", value: restaurantId });
  }
  const location =
    presentText(venue.location?.outlet) || presentText(venue.location?.locality) || presentText(venue.location?.city);
  if (location && !isDistanceText(location)) {
    fields.push({ label: "Location", value: location, kind: "location" });
  }
  const address = presentText(venue.location?.address);
  if (address && address !== location && !isDistanceText(address)) {
    fields.push({ label: "Address", value: address, kind: "location" });
  }
  if (venue.rating != null) {
    const count = presentText(venue.rating_count);
    fields.push({
      label: "Rating",
      value: count ? `${venue.rating} (${count})` : String(venue.rating),
      kind: "rating",
    });
  }
  const cuisines = (venue.cuisines || []).map((item) => item.trim()).filter(Boolean);
  if (cuisines.length) {
    fields.push({ label: "Cuisine", value: cuisines.join(", ") });
  }
  const price = presentText(venue.price_for_two);
  if (price) {
    fields.push({ label: "Price for two", value: price });
  }
  const status = presentText(venue.opening_status);
  if (status) {
    fields.push({ label: "Opening status", value: status });
  }
  const hours = presentText(venue.opening_hours);
  if (hours && hours !== status) {
    fields.push({ label: "Opening hours", value: hours });
  }
  const phone = presentText(venue.phone) || presentText(venue.actions?.call);
  if (phone) {
    fields.push({ label: "Phone", value: phone, href: `tel:${phone.replace(/\s+/g, "")}`, kind: "phone" });
  }
  const source = presentText(venue.source_url) || presentText(fallbackUrl);
  if (source) {
    fields.push({ label: "Source URL", value: source, href: source, kind: "link" });
  }
  return fields;
}

export function dineoutListMetrics(venue: DineoutVenue | null | undefined) {
  const photos = venue?.gallery_images?.length || venue?.photos?.length || 0;
  const menu = venue?.menu_pages?.length || 0;
  const offers = (venue?.offers || []).filter((offer) => presentText(offer.title) && !isDiscoveryOfferTitle(offer.title)).length;
  return {
    photos: photos || null,
    menu: menu || null,
    offers: offers || null,
    rating: venue?.rating ?? null,
    ratingCount: presentText(venue?.rating_count),
  };
}

export function isDiscoveryOfferTitle(title: string | null | undefined): boolean {
  const text = (title || "").trim().toLowerCase();
  if (!text) {
    return true;
  }
  if (["photos", "gallery", "menu", "location", "amenities"].includes(text)) {
    return true;
  }
  return /recommended|nearby|more american|brands near|similar restaurant|explore more|restaurants near|^near\b/.test(
    text,
  );
}

export function resolveDineout(result: CatalogCreateResponse): DineoutVenue | null {
  if (result.dineout && Object.keys(result.dineout).length > 0) {
    return result.dineout;
  }
  const type = catalogueType(result.catalogue_type);
  if (type !== "dineout" && type !== "both") {
    return null;
  }
  const restaurant = result.restaurant;
  if (!restaurant) {
    return null;
  }
  return {
    venue: restaurant.name,
    hero_image: restaurant.image_url,
    rating: restaurant.rating,
    rating_count: restaurant.rating_count,
    cuisines: restaurant.cuisines,
    price_for_two: restaurant.price_for_two,
    location: {
      address: restaurant.address,
      outlet: restaurant.outlet,
    },
    photos: restaurant.image_url ? [restaurant.image_url] : undefined,
    source_url: result.source_url,
  };
}

export function catalogueMatchesDomain(result: CatalogCreateResponse, domain: "restaurant" | "dineout"): boolean {
  const type = catalogueType(result.catalogue_type);
  return type === "both" || type === domain;
}

export function overviewStats(catalogues: StoredCatalogue[]) {
  const ready = catalogues.filter((row) => row.result.extraction_status === "ok");
  return {
    total: catalogues.length,
    restaurant: catalogues.filter((row) => catalogueType(row.result.catalogue_type) === "restaurant").length,
    dineout: catalogues.filter((row) => catalogueType(row.result.catalogue_type) === "dineout").length,
    both: catalogues.filter((row) => catalogueType(row.result.catalogue_type) === "both").length,
    swiggy: catalogues.filter((row) => cataloguePlatform(row.result) === "swiggy").length,
    zomato: catalogues.filter((row) => cataloguePlatform(row.result) === "zomato").length,
    magicpin: catalogues.filter((row) => cataloguePlatform(row.result) === "magicpin").length,
    items: ready.reduce((sum, row) => sum + (row.result.item_count || 0), 0),
    images: ready.reduce((sum, row) => sum + (row.result.image_count || 0), 0),
  };
}
