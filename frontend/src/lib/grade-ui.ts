import type { CatalogCreateResponse, CatalogueCategory, CatalogueItem } from "@/lib/catalog-types";
import type { GradeFinding, GradeLetter } from "@/lib/grade-types";
import { hasProductImage } from "@/lib/catalogue-menu";

export type AffectedProduct = {
  path: string;
  name: string;
  category: string;
  imageUrl: string | null;
  description: string;
};

const CHECK_TITLE: Record<string, string> = {
  missing_description: "Missing descriptions",
  description_coverage: "Description coverage",
  placeholder_text: "Placeholder descriptions",
  malformed_text: "Unclear descriptions",
  repeated_description: "Duplicate descriptions",
  missing_category_name: "Category names",
  category_count_mismatch: "Category item counts",
  empty_item_labels: "Missing labels",
  missing_item_image: "Missing photos",
  image_missing: "Missing photos",
  image_invalid: "Unusable photos",
  image_unreadable: "Unreadable photos",
  image_low_quality: "Low-quality photos",
  no_images_present: "Missing photos",
  missing_price: "Missing prices",
  invalid_price: "Invalid prices",
};

const ITEM_PATH = /^(?:menus\[\d+]\.)?categories\[(\d+)]\.items\[(\d+)]/;
const CATEGORY_PATH = /^(?:menus\[\d+]\.)?categories\[(\d+)](?!\.items)/;

export function checkTitle(checkId: string): string {
  return CHECK_TITLE[checkId] || "Catalogue quality issue";
}

export function letterBadgeClass(letter: GradeLetter): string {
  if (letter === "A") {
    return "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (letter === "B") {
    return "bg-sky-50 text-sky-800 dark:bg-sky-950 dark:text-sky-200";
  }
  if (letter === "C") {
    return "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200";
  }
  if (letter === "D") {
    return "bg-orange-50 text-orange-800 dark:bg-orange-950 dark:text-orange-200";
  }
  return "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200";
}

export function gradeHeadline(letter: GradeLetter): string {
  if (letter === "A") {
    return "Your catalogue is in strong shape.";
  }
  if (letter === "B") {
    return "Your catalogue is good, with a few important improvements.";
  }
  if (letter === "C") {
    return "Your catalogue is usable, but several listings need attention.";
  }
  if (letter === "D") {
    return "Your catalogue needs substantial listing improvements.";
  }
  return "Your catalogue has serious listing-quality gaps.";
}

export function sectionOperatorLabel(section: string, fallback: string): string {
  if (section === "deterministic") {
    return "Catalogue data";
  }
  if (section === "nlp") {
    return "Descriptions";
  }
  if (section === "vision") {
    return "Images";
  }
  return fallback;
}

export function formatMeasuredValue(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    if (value > 0 && value <= 1) {
      return `${Math.round(value * 100)}%`;
    }
    if (Number.isInteger(value)) {
      return String(value);
    }
    return String(Math.round(value * 10) / 10);
  }
  if (typeof value === "string" && value.trim()) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric > 0 && numeric <= 1) {
      return `${Math.round(numeric * 100)}%`;
    }
    return value;
  }
  return null;
}

export function humanFailureReason(reason: string | null | undefined): string {
  const text = (reason || "").toLowerCase();
  if (text.includes("hallucin")) {
    return "Baba couldn't safely generate this description. The catalogue doesn't include enough facts to write it without guessing.";
  }
  if (text.includes("claim") || text.includes("unsupported")) {
    return "Baba couldn't safely generate this suggestion due to unsupported claims in the generated copy.";
  }
  if (text.includes("ollama") || text.includes("unavailable") || text.includes("timeout")) {
    return "Ollama local LLM is currently unavailable or timed out. Ensure Ollama is running at 127.0.0.1:11434 with llama3:latest.";
  }
  if (!reason) {
    return "Baba couldn't safely generate this suggestion from the available catalogue information.";
  }
  return `Generation failed: ${reason}`;
}

function itemAt(catalogue: CatalogCreateResponse, categoryIndex: number, itemIndex: number): AffectedProduct | null {
  const category = catalogue.categories?.[categoryIndex];
  const item = category?.items[itemIndex];
  if (!category || !item) {
    return null;
  }
  return productFromItem(item, category, `categories[${categoryIndex}].items[${itemIndex}]`);
}

export function productFromItem(item: CatalogueItem, category: CatalogueCategory, path: string): AffectedProduct {
  return {
    path,
    name: (item.name || "Untitled item").trim() || "Untitled item",
    category: (category.name || "Uncategorised").trim() || "Uncategorised",
    imageUrl: hasProductImage(item) ? item.image_url!.trim() : null,
    description: (item.description || "").trim(),
  };
}

export function resolvePathProduct(catalogue: CatalogCreateResponse | null | undefined, path: string): AffectedProduct | null {
  if (!catalogue) {
    return null;
  }
  const itemMatch = ITEM_PATH.exec(path);
  if (itemMatch) {
    return itemAt(catalogue, Number(itemMatch[1]), Number(itemMatch[2]));
  }
  const categoryMatch = CATEGORY_PATH.exec(path);
  if (categoryMatch) {
    const category = catalogue.categories?.[Number(categoryMatch[1])];
    if (!category) {
      return null;
    }
    return {
      path,
      name: (category.name || "Unnamed category").trim() || "Unnamed category",
      category: "Category",
      imageUrl: null,
      description: `${category.items.length} items`,
    };
  }
  return null;
}

function itemsMissingDescription(catalogue: CatalogCreateResponse): AffectedProduct[] {
  const rows: AffectedProduct[] = [];
  (catalogue.categories || []).forEach((category, categoryIndex) => {
    category.items.forEach((item, itemIndex) => {
      if (!(item.description || "").trim()) {
        rows.push(productFromItem(item, category, `categories[${categoryIndex}].items[${itemIndex}]`));
      }
    });
  });
  return rows;
}

function itemsMissingImage(catalogue: CatalogCreateResponse): AffectedProduct[] {
  const rows: AffectedProduct[] = [];
  (catalogue.categories || []).forEach((category, categoryIndex) => {
    category.items.forEach((item, itemIndex) => {
      if (!hasProductImage(item)) {
        rows.push(productFromItem(item, category, `categories[${categoryIndex}].items[${itemIndex}]`));
      }
    });
  });
  return rows;
}

export function resolveFindingProducts(
  finding: GradeFinding,
  catalogue: CatalogCreateResponse | null | undefined,
): AffectedProduct[] {
  const fromPaths = finding.evidence.paths
    .map((path) => resolvePathProduct(catalogue, path))
    .filter((row): row is AffectedProduct => Boolean(row));
  if (fromPaths.length) {
    const unique = new Map<string, AffectedProduct>();
    fromPaths.forEach((row) => unique.set(row.path, row));
    return [...unique.values()];
  }
  if (!catalogue) {
    return [];
  }
  if (finding.check_id === "missing_description" || finding.check_id === "description_coverage") {
    return itemsMissingDescription(catalogue);
  }
  if (
    finding.check_id === "missing_item_image" ||
    finding.check_id === "image_missing" ||
    finding.check_id === "no_images_present"
  ) {
    return itemsMissingImage(catalogue);
  }
  if (finding.check_id === "repeated_description") {
    const groups = new Map<string, AffectedProduct[]>();
    (catalogue.categories || []).forEach((category, categoryIndex) => {
      category.items.forEach((item, itemIndex) => {
        const description = (item.description || "").trim().toLowerCase();
        if (!description) {
          return;
        }
        const row = productFromItem(item, category, `categories[${categoryIndex}].items[${itemIndex}]`);
        const list = groups.get(description) || [];
        list.push(row);
        groups.set(description, list);
      });
    });
    return [...groups.values()].filter((group) => group.length > 1).flat();
  }
  return [];
}

export function findingSummary(finding: GradeFinding, products: AffectedProduct[]): string {
  const count = products.length || finding.evidence.affected_count;
  if (finding.check_id === "missing_description" || finding.check_id === "description_coverage") {
    return `${count} ${count === 1 ? "item has" : "items have"} no description.`;
  }
  if (finding.check_id === "repeated_description") {
    return `${count} items share the same description.`;
  }
  if (finding.check_id.includes("image")) {
    return `${count} ${count === 1 ? "photo needs" : "photos need"} improvement.`;
  }
  if (finding.check_id === "missing_category_name") {
    return `${count} ${count === 1 ? "category is" : "categories are"} missing a name.`;
  }
  if (finding.check_id === "category_count_mismatch") {
    return `${count} ${count === 1 ? "category has" : "categories have"} a declared item count that does not match the items listed.`;
  }
  if (finding.check_id === "empty_item_labels") {
    return `${count} ${count === 1 ? "item is" : "items are"} missing labels.`;
  }
  return finding.recommendation?.action || finding.why;
}
