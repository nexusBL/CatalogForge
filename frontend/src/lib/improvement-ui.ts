import type { GradeExplanation, GradeFinding } from "@/lib/grade-types";
import type { ImprovementKind } from "@/lib/improvement-types";
import { PHASE6_V1_CHECK_IDS } from "@/lib/improvement-types";

export const IMPROVEMENT_KIND_LABEL: Record<ImprovementKind, string> = {
  description: "Description",
  category_name: "Category name",
  labels: "Labels",
  media_handoff: "Image / video (Phase 7 handoff)",
  item_price: "Price",
};

const CHECK_KIND: Record<string, ImprovementKind> = {
  missing_description: "description",
  description_coverage: "description",
  placeholder_text: "description",
  malformed_text: "description",
  repeated_description: "description",
  missing_category_name: "category_name",
  empty_item_labels: "labels",
  missing_item_image: "media_handoff",
  image_missing: "media_handoff",
  image_invalid: "media_handoff",
  image_unreadable: "media_handoff",
  image_low_quality: "media_handoff",
  no_images_present: "media_handoff",
  missing_price: "item_price",
  invalid_price: "item_price",
};

export function kindForCheckId(checkId: string): ImprovementKind | null {
  return CHECK_KIND[checkId] ?? null;
}

export function isSupportedImprovementCheck(checkId: string): boolean {
  return PHASE6_V1_CHECK_IDS.has(checkId);
}

export function catalogueGradeHref(catalogueId: string): string {
  return `/catalogues/${catalogueId}`;
}

export function catalogueImprovementsHref(catalogueId: string, checkId?: string): string {
  const base = `/catalogues/${catalogueId}/improvements`;
  if (!checkId) {
    return base;
  }
  return `${base}?check_id=${encodeURIComponent(checkId)}`;
}

export function improvementRequestPaths(finding: GradeFinding): string[] | undefined {
  const itemPaths = finding.evidence.paths.filter(
    (path) =>
      path.includes(".items[") ||
      path.endsWith(".description") ||
      path.endsWith(".name") ||
      path.endsWith(".image_url") ||
      path.endsWith(".price") ||
      path.endsWith(".labels") ||
      path === "venue.image_url" ||
      path === "catalogue.images",
  );
  const paths = itemPaths.slice(0, 5);
  return paths.length ? paths : undefined;
}

export function supportedImprovementFindings(explanation: GradeExplanation | null): GradeFinding[] {
  if (!explanation) {
    return [];
  }
  return explanation.findings.filter((finding) => isSupportedImprovementCheck(finding.check_id));
}
