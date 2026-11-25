import type { CatalogCreateResponse } from "@/lib/catalog-types";
import { cataloguePlatform, platformLabel } from "@/lib/catalog-types";
import type { GradeLetter } from "@/lib/grade-types";
import { catalogueType, catalogueTypeLabel, presentText, venueDisplayName, venueLocation } from "@/lib/restaurant-identity";

export const GRADE_FILTER_LETTERS: GradeLetter[] = ["F", "D", "C", "B", "A"];

export type GradeListFilter = GradeLetter | "all" | "ungraded";
export type VenueDomainFilter = "all" | "restaurant" | "dineout";
export type GradingWorkspaceTab = "quality" | "photos" | "video";

export type GradingListRow = {
  id: string;
  name: string;
  location: string | null;
  type: "restaurant" | "dineout" | "both";
  typeLabel: string;
  platformLabel: string;
  thumbnail: string | null;
  letter: GradeLetter | null;
  score: number | null;
};

export function gradingListHref(): string {
  return "/grading";
}

export function gradingWorkspaceHref(catalogueId: string, tab?: GradingWorkspaceTab): string {
  const base = `/grading/${catalogueId}`;
  if (!tab || tab === "quality") {
    return base;
  }
  return `${base}?tab=${encodeURIComponent(tab)}`;
}

export function venueThumbnail(result: CatalogCreateResponse): string | null {
  const type = catalogueType(result.catalogue_type);
  if (type === "dineout") {
    return presentText(result.dineout?.hero_image) || presentText(result.restaurant?.image_url);
  }
  return presentText(result.restaurant?.image_url) || presentText(result.dineout?.hero_image);
}

export function gradingRowFromCatalogue(
  id: string,
  result: CatalogCreateResponse,
  letter: GradeLetter | null,
  score: number | null,
): GradingListRow {
  const type = catalogueType(result.catalogue_type);
  return {
    id,
    name: venueDisplayName(result),
    location: venueLocation(result),
    type,
    typeLabel: catalogueTypeLabel(type),
    platformLabel: platformLabel(cataloguePlatform(result)),
    thumbnail: venueThumbnail(result),
    letter,
    score,
  };
}

export function filterGradingRows(
  rows: GradingListRow[],
  domain: VenueDomainFilter,
  grade: GradeListFilter,
): GradingListRow[] {
  return rows.filter((row) => {
    const domainOk = domain === "all" || row.type === domain || row.type === "both";
    if (!domainOk) {
      return false;
    }
    if (grade === "all") {
      return true;
    }
    if (grade === "ungraded") {
      return row.letter === null;
    }
    return row.letter === grade;
  });
}

export function parseGradingTab(value: string | null | undefined): GradingWorkspaceTab {
  if (value === "photos" || value === "video") {
    return value;
  }
  return "quality";
}
