import type { CatalogueType, Platform, StoredCatalogue } from "@/lib/catalog-types";
import { cataloguePlatform, platformLabel } from "@/lib/catalog-types";
import {
  catalogueMatchesDomain,
  catalogueType,
  catalogueTypeLabel,
  outletIdentity,
  venueDisplayName,
  venueLocation,
} from "@/lib/restaurant-identity";

export const PLATFORMS: Platform[] = ["swiggy", "zomato", "magicpin"];
export const CATALOGUE_TYPES: CatalogueType[] = ["restaurant", "dineout", "both"];

export function createCatalogueHref(platform?: Platform, type?: CatalogueType): string {
  const params = new URLSearchParams();
  if (platform) {
    params.set("platform", platform);
  }
  if (type) {
    params.set("catalogue_type", type);
  }
  const query = params.toString();
  return query ? `/catalogues/new?${query}` : "/catalogues/new";
}

export function cataloguesHref(filters?: { platform?: Platform; type?: CatalogueType }): string {
  const params = new URLSearchParams();
  if (filters?.platform) {
    params.set("platform", filters.platform);
  }
  if (filters?.type) {
    params.set("type", filters.type);
  }
  const query = params.toString();
  return query ? `/catalogues?${query}` : "/catalogues";
}

export function cataloguesForDomain(
  rows: StoredCatalogue[],
  domain: "restaurant" | "dineout",
): StoredCatalogue[] {
  return rows.filter((row) => catalogueMatchesDomain(row.result, domain));
}

export function filterStoredCatalogues(
  rows: StoredCatalogue[],
  filters?: { platform?: Platform | null; type?: CatalogueType | null },
): StoredCatalogue[] {
  return rows.filter((row) => {
    if (filters?.platform && cataloguePlatform(row.result) !== filters.platform) {
      return false;
    }
    if (filters?.type) {
      const type = catalogueType(row.result.catalogue_type);
      if (filters.type === "both") {
        return type === "both";
      }
      if (type !== filters.type && type !== "both") {
        return false;
      }
    }
    return true;
  });
}

export function navCatalogueItem(row: StoredCatalogue) {
  const name = venueDisplayName(row.result);
  const location = venueLocation(row.result);
  const platform = cataloguePlatform(row.result);
  const type = catalogueType(row.result.catalogue_type);
  return {
    id: row.id,
    href: `/catalogues/${row.id}`,
    name,
    location,
    platform,
    platformLabel: platformLabel(platform),
    type,
    typeLabel: catalogueTypeLabel(type),
    identity: outletIdentity(name, location),
    subtitle: [location, platformLabel(platform), catalogueTypeLabel(type)].filter(Boolean).join(" · "),
  };
}
