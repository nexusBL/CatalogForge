export type ExtractionStatus = "ok" | "partial" | "blocked" | "failed" | "pending";

export type CatalogueType = "restaurant" | "dineout" | "both";

export type Platform = "swiggy" | "zomato" | "magicpin";

export const PLATFORM_LABEL: Record<Platform, string> = {
  swiggy: "Swiggy",
  zomato: "Zomato",
  magicpin: "Magicpin",
};

export function platformLabel(value: string | null | undefined): string {
  if (value === "zomato" || value === "magicpin" || value === "swiggy") {
    return PLATFORM_LABEL[value];
  }
  return PLATFORM_LABEL.swiggy;
}

export function cataloguePlatform(input?: { platform?: string | null; source_url?: string | null }): Platform {
  const explicit = (input?.platform || "").trim().toLowerCase();
  if (explicit === "swiggy" || explicit === "zomato" || explicit === "magicpin") {
    return explicit;
  }
  const url = (input?.source_url || "").toLowerCase();
  if (url.includes("zomato.com")) {
    return "zomato";
  }
  if (url.includes("magicpin.in")) {
    return "magicpin";
  }
  return "swiggy";
}

export type CatalogueItem = {
  name: string;
  description?: string | null;
  price?: number | string | null;
  original_price?: number | string | null;
  food_type?: string | null;
  rating?: number | null;
  rating_count?: number | string | null;
  labels?: string[];
  variants?: unknown[];
  customizations?: unknown[];
  image_url?: string | null;
  source_image_url?: string | null;
  nutritional_information?: unknown;
  additional_information?: Record<string, unknown>;
  is_bestseller?: boolean;
  available?: boolean | null;
  next_available?: string | null;
  item_id?: string | null;
  source_item_id?: string | null;
  id?: string | null;
};

export type CatalogueCategory = {
  name: string;
  items: CatalogueItem[];
  item_count?: number | null;
};

export type CatalogueRestaurant = {
  name?: string | null;
  rating?: number | null;
  rating_count?: number | string | null;
  price_for_two?: string | number | null;
  cuisines?: string[];
  outlet?: string | null;
  address?: string | null;
  fssai_license?: string | null;
  image_url?: string | null;
  offers?: unknown[];
  zomato_rating?: number | null;
  zomato_url?: string | null;
  magicpin_rating?: number | null;
  magicpin_url?: string | null;
};

export type DineoutOffer = {
  title: string;
  description?: string | null;
  discount?: string | null;
  terms?: string | null;
  validity?: string | null;
  code?: string | null;
  type?: string | null;
  image?: string | null;
  source_image_url?: string | null;
};

export type DineoutMenuPage = {
  title: string;
  image?: string | null;
  images?: string[];
  page_count?: number | null;
  source_url?: string | null;
  identity?: string | null;
};

export type DineoutGalleryImage = {
  url: string;
  category?: string | null;
};

export type DineoutLocation = {
  address?: string | null;
  locality?: string | null;
  city?: string | null;
  outlet?: string | null;
  distance?: string | null;
  location?: string | null;
  map_image?: string | null;
  maps_url?: string | null;
};

export type DineoutVenue = {
  venue?: string | null;
  restaurant_id?: string | null;
  hero_image?: string | null;
  rating?: number | null;
  rating_count?: number | string | null;
  cuisines?: string[];
  price_for_two?: string | number | null;
  opening_hours?: string | null;
  opening_status?: string | null;
  actions?: {
    directions?: string | null;
    call?: string | null;
  } | null;
  offers?: DineoutOffer[];
  menu_pages?: DineoutMenuPage[];
  popular_dishes?: string[];
  photos?: string[];
  gallery_images?: DineoutGalleryImage[];
  videos?: Array<{ source_url: string; thumbnail?: string | null; title?: string | null }>;
  amenities?: string[];
  location?: DineoutLocation | null;
  location_map_image?: string | null;
  directions_url?: string | null;
  phone?: string | null;
  source_url?: string | null;
};

export type CatalogCreateResponse = {
  extraction_status: ExtractionStatus;
  source_type?: string | null;
  restaurant_name: string;
  fssai_number: string;
  source_url: string;
  platform?: Platform;
  catalogue_type?: CatalogueType;
  restaurant?: CatalogueRestaurant | null;
  dineout?: DineoutVenue | null;
  categories?: CatalogueCategory[];
  item_count?: number;
  image_count?: number;
  error?: string | null;
  access_method?: string | null;
  id?: string | null;
  organization_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  venue_id?: string | null;
  schema_version?: number | null;
};

export type StoredCatalogue = {
  id: string;
  organizationId: string;
  createdAt: string;
  result: CatalogCreateResponse;
  headRevision?: number;
  stateHash?: string;
};

export type CatalogueListResponse = {
  catalogues: Array<{
    id: string;
    organization_id: string;
    created_at: string;
    result: CatalogCreateResponse;
    head_revision?: number | null;
    state_hash?: string | null;
  }>;
};

export function toStoredCatalogue(row: CatalogueListResponse["catalogues"][number]): StoredCatalogue {
  return {
    id: row.id,
    organizationId: row.organization_id,
    createdAt: row.created_at,
    result: row.result,
    headRevision: row.head_revision ?? undefined,
    stateHash: row.state_hash ?? undefined,
  };
}

export function extractionMessage(
  status: ExtractionStatus,
  error?: string | null,
  platform?: string | null,
): string {
  const label = platformLabel(cataloguePlatform({ platform }));
  if (status === "blocked") {
    return `${label} could not be accessed right now.`;
  }
  if (error) {
    return error;
  }
  if (status === "failed") {
    return "Catalogue extraction failed. No fake menu data is shown.";
  }
  if (status === "pending") {
    return "Official API access is not configured yet. Extraction is pending credentials.";
  }
  return "Catalogue created.";
}
