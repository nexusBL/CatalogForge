import type { CatalogCreateResponse, CatalogueItem } from "@/lib/catalog-types";
import type { GradeExplanation, GradeFinding, GradeLetter } from "@/lib/grade-types";
import { hasProductImage } from "@/lib/catalogue-menu";

export type QualityAspectKey = "description" | "labels" | "image" | "price";

export type ItemQualityAspect = {
  key: QualityAspectKey;
  label: string;
  letter: GradeLetter;
  status: string;
  checkId: string | null;
  path: string;
  canImprove: boolean;
};

export type ItemQualityRow = {
  name: string;
  category: string;
  imageUrl: string | null;
  itemPath: string;
  aspects: ItemQualityAspect[];
  weakCount: number;
};

const ITEM_PATH = /^(?:menus\[\d+]\.)?categories\[(\d+)]\.items\[(\d+)]/;

const DESCRIPTION_CHECKS = new Set([
  "missing_description",
  "description_coverage",
  "placeholder_text",
  "malformed_text",
  "repeated_description",
]);
const LABEL_CHECKS = new Set(["empty_item_labels"]);
const IMAGE_CHECKS = new Set([
  "missing_item_image",
  "image_missing",
  "image_invalid",
  "image_unreadable",
  "image_low_quality",
  "no_images_present",
]);
const PRICE_CHECKS = new Set(["missing_price", "invalid_price"]);

function letterForMissing(hasValue: boolean): GradeLetter {
  return hasValue ? "A" : "F";
}

function letterFromFinding(finding: GradeFinding | undefined, fallback: GradeLetter): GradeLetter {
  if (!finding) {
    return fallback;
  }
  if (
    finding.severity === "hard" ||
    finding.check_id === "missing_description" ||
    finding.check_id === "missing_item_image" ||
    finding.check_id === "image_missing" ||
    finding.check_id === "no_images_present" ||
    finding.check_id === "empty_item_labels" ||
    finding.check_id === "missing_price"
  ) {
    return "F";
  }
  if (
    finding.check_id.includes("low_quality") ||
    finding.check_id.includes("placeholder") ||
    finding.check_id.includes("repeated") ||
    finding.check_id.includes("invalid") ||
    finding.check_id.includes("unreadable") ||
    finding.check_id.includes("coverage") ||
    finding.check_id.includes("malformed")
  ) {
    return "D";
  }
  return "D";
}

function findingFor(
  findings: GradeFinding[],
  categoryIndex: number,
  itemIndex: number,
  checks: Set<string>,
): GradeFinding | undefined {
  const needle = `categories[${categoryIndex}].items[${itemIndex}]`;
  return findings.find((finding) => {
    if (!checks.has(finding.check_id) || finding.result !== "fail") {
      return false;
    }
    return finding.evidence.paths.some((path) => {
      const match = ITEM_PATH.exec(path);
      if (!match) {
        return path.includes(needle);
      }
      return Number(match[1]) === categoryIndex && Number(match[2]) === itemIndex;
    });
  });
}

function labelsOf(item: CatalogueItem): string[] {
  return (item.labels || []).map((label) => String(label).trim()).filter(Boolean);
}

export function itemQualityRows(
  catalogue: CatalogCreateResponse | null | undefined,
  explanation: GradeExplanation | null | undefined,
): ItemQualityRow[] {
  const findings = explanation?.findings ?? [];
  const rows: ItemQualityRow[] = [];
  (catalogue?.categories || []).forEach((category, categoryIndex) => {
    (category.items || []).forEach((item, itemIndex) => {
      const base = `menus[0].categories[${categoryIndex}].items[${itemIndex}]`;
      const description = (item.description || "").trim();
      const labels = labelsOf(item);
      const hasImage = hasProductImage(item);
      const hasPrice = item.price != null && String(item.price).trim() !== "";
      const descriptionFinding = findingFor(findings, categoryIndex, itemIndex, DESCRIPTION_CHECKS);
      const labelFinding = findingFor(findings, categoryIndex, itemIndex, LABEL_CHECKS);
      const imageFinding = findingFor(findings, categoryIndex, itemIndex, IMAGE_CHECKS);
      const priceFinding = findingFor(findings, categoryIndex, itemIndex, PRICE_CHECKS);
      const aspects: ItemQualityAspect[] = [
        {
          key: "description",
          label: "Description",
          letter: letterFromFinding(descriptionFinding, letterForMissing(Boolean(description))),
          status: descriptionFinding
            ? "Needs a better description"
            : description
              ? "Present"
              : "Missing",
          checkId: description ? descriptionFinding?.check_id ?? "description_coverage" : "missing_description",
          path: `${base}.description`,
          canImprove: true,
        },
        {
          key: "labels",
          label: "Tags",
          letter: letterFromFinding(labelFinding, letterForMissing(labels.length > 0)),
          status: labels.length ? labels.join(", ") : "Missing",
          checkId: "empty_item_labels",
          path: `${base}.labels`,
          canImprove: true,
        },
        {
          key: "image",
          label: "Image",
          letter: letterFromFinding(imageFinding, letterForMissing(hasImage)),
          status: imageFinding ? "Needs a better photo" : hasImage ? "Present" : "Missing",
          checkId: hasImage ? imageFinding?.check_id ?? "image_low_quality" : "missing_item_image",
          path: `${base}.image_url`,
          canImprove: true,
        },
        {
          key: "price",
          label: "Price",
          letter: letterFromFinding(priceFinding, letterForMissing(hasPrice)),
          status: hasPrice ? String(item.price) : "Missing",
          checkId: hasPrice ? priceFinding?.check_id ?? null : "missing_price",
          path: `${base}.price`,
          canImprove: Boolean(item.original_price),
        },
      ];
      rows.push({
        name: (item.name || "Untitled item").trim() || "Untitled item",
        category: (category.name || "Uncategorised").trim() || "Uncategorised",
        imageUrl: hasImage ? String(item.image_url).trim() : null,
        itemPath: base,
        aspects,
        weakCount: aspects.filter((aspect) => aspect.letter !== "A" && aspect.letter !== "B").length,
      });
    });
  });
  return rows.sort((left, right) => right.weakCount - left.weakCount || left.name.localeCompare(right.name));
}
