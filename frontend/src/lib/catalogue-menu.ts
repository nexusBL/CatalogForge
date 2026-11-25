import type { CatalogueCategory, CatalogueItem } from "@/lib/catalog-types";

export const ALL_CATEGORIES = "all";
export const FOOD_FILTER_ALL = "all";
export const FOOD_FILTER_VEG = "veg";
export const FOOD_FILTER_NONVEG = "nonveg";

export type FoodFilter = typeof FOOD_FILTER_ALL | typeof FOOD_FILTER_VEG | typeof FOOD_FILTER_NONVEG;

export type IdentifiedItem = CatalogueItem & { key: string };
export type IdentifiedCategory = Omit<CatalogueCategory, "items"> & {
  key: string;
  sourceIndex: number;
  items: IdentifiedItem[];
};

export type ImageFilter = "all" | "with" | "without";

export type MenuGroup = {
  name: string;
  options: Array<{ name: string; price?: string | null; amount: number; id: string }>;
};

export function addonAmount(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return value >= 1000 && value % 100 === 0 ? value / 100 : value;
  }
  if (typeof value === "string") {
    const digits = value.replace(/[^\d.]/g, "");
    if (!digits) {
      return 0;
    }
    const parsed = Number(digits);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function sellingAmount(item: CatalogueItem): number {
  if (typeof item.price === "number" && Number.isFinite(item.price)) {
    return item.price;
  }
  return addonAmount(item.price);
}

export function mrpAmount(item: CatalogueItem): number | null {
  if (item.original_price == null || item.original_price === "") {
    return null;
  }
  if (typeof item.original_price === "number" && Number.isFinite(item.original_price)) {
    return item.original_price;
  }
  const amount = addonAmount(item.original_price);
  return amount > 0 ? amount : null;
}

export function discountLabel(item: CatalogueItem): string | null {
  const selling = sellingAmount(item);
  const mrp = mrpAmount(item);
  if (mrp == null || selling <= 0 || mrp <= selling) {
    return null;
  }
  const off = mrp - selling;
  const percent = Math.round((off / mrp) * 100);
  return percent > 0 ? `${percent}% off` : null;
}

export function hasProductImage(item: CatalogueItem): boolean {
  const url = item.image_url?.trim();
  if (!url) {
    return false;
  }
  if (/veg-icon|non-veg-icon|egg-icon|star-filled|star-empty|web\/assets|web_assets/i.test(url)) {
    return false;
  }
  return /^https?:\/\//i.test(url) || url.startsWith("/catalogue-assets/");
}

export function isBestseller(item: CatalogueItem): boolean {
  if (item.is_bestseller === true) {
    return true;
  }
  if (item.additional_information?.isBestseller === true || item.additional_information?.isBestseller === 1) {
    return true;
  }
  return (item.labels || []).some((label) => String(label).toLowerCase().replace(/\s+/g, "").includes("bestseller"));
}

export function isItemAvailable(item: CatalogueItem): boolean {
  if (item.available === false) {
    return false;
  }
  const extra = item.additional_information;
  if (extra && (extra.inStock === 0 || extra.inStock === false || extra.inStock === "0")) {
    return false;
  }
  return true;
}

export function nextAvailableLabel(item: CatalogueItem): string | null {
  if (item.next_available && item.next_available.trim()) {
    const text = item.next_available.trim();
    return /next available/i.test(text) ? text : `Next available at ${text}`;
  }
  return null;
}

export function matchesImageFilter(item: CatalogueItem, imageFilter: ImageFilter): boolean {
  if (imageFilter === "all") {
    return true;
  }
  return imageFilter === "with" ? hasProductImage(item) : !hasProductImage(item);
}

export function matchesBestsellerFilter(item: CatalogueItem, bestsellerOnly: boolean): boolean {
  return !bestsellerOnly || isBestseller(item);
}

export function sourceItemId(item: CatalogueItem): string | null {
  if (item.source_item_id != null && item.source_item_id !== "") {
    return String(item.source_item_id);
  }
  const extra = item.additional_information;
  const value = extra && typeof extra === "object" ? extra.id : undefined;
  if (value == null || value === "") {
    return null;
  }
  return String(value);
}

export function identifyCatalogue(categories: CatalogueCategory[]): IdentifiedCategory[] {
  const usedItemKeys = new Set<string>();
  return categories.map((category, categoryIndex) => ({
    ...category,
    key: `category-${categoryIndex}`,
    sourceIndex: categoryIndex,
    items: category.items.map((item, itemIndex) => {
      const internalId = typeof item.item_id === "string" && item.item_id.trim() ? item.item_id.trim() : null;
      const sourceId = sourceItemId(item);
      let key = internalId ? `item-${internalId}` : sourceId ? `item-${sourceId}` : `item-${categoryIndex}-${itemIndex}`;
      if (usedItemKeys.has(key)) {
        key = `${key}-${categoryIndex}-${itemIndex}`;
      }
      usedItemKeys.add(key);
      return { ...item, key };
    }),
  }));
}

export function categoryAnchor(name: string, index: number): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `category-${index}-${slug || "section"}`;
}

export function formatPrice(value: number | string | null | undefined): string | null {
  if (value == null || value === "") {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return `₹${Number.isInteger(value) ? value : value.toFixed(2)}`;
  }
  const text = String(value).trim();
  if (!text) {
    return null;
  }
  return /₹|rs\.?/i.test(text) ? text : `₹${text}`;
}

export function formatStoredAddonPrice(value: unknown): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return formatPrice(typeof value === "string" ? value : null);
  }
  const amount = value >= 1000 && value % 100 === 0 ? value / 100 : value;
  return formatPrice(amount);
}

export function isVeg(foodType: string | null | undefined): boolean | null {
  if (!foodType) {
    return null;
  }
  const value = foodType.toLowerCase().replace(/[^a-z]/g, "");
  if (value === "veg" || value === "vegetarian") {
    return true;
  }
  if (value.includes("nonveg") || value.includes("nonvegetarian") || value === "egg") {
    return false;
  }
  return null;
}

export function matchesFoodFilter(item: CatalogueItem, foodFilter: FoodFilter): boolean {
  if (foodFilter === FOOD_FILTER_ALL) {
    return true;
  }
  const veg = isVeg(item.food_type);
  if (veg == null) {
    return false;
  }
  return foodFilter === FOOD_FILTER_VEG ? veg : !veg;
}

export function isCustomizable(item: CatalogueItem): boolean {
  return Boolean(
    (item.variants && item.variants.length > 0) || (item.customizations && item.customizations.length > 0),
  );
}

export function matchesQuery(item: CatalogueItem, categoryName: string, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystack = [item.name, item.description || "", categoryName, ...(item.labels || [])]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

export function filterCatalogue(
  categories: CatalogueCategory[] | IdentifiedCategory[],
  query: string,
  selectedCategory: string = ALL_CATEGORIES,
  foodFilter: FoodFilter = FOOD_FILTER_ALL,
  imageFilter: ImageFilter = "all",
  bestsellerOnly = false,
): IdentifiedCategory[] {
  const source = categories as IdentifiedCategory[];
  const identified =
    source.length > 0 && typeof source[0]?.key === "string" && typeof source[0]?.sourceIndex === "number"
      ? source
      : identifyCatalogue(categories);
  const matched = identified
    .filter((category) => selectedCategory === ALL_CATEGORIES || category.key === selectedCategory)
    .map((category): IdentifiedCategory => ({
      ...category,
      items: category.items.filter(
        (item): item is IdentifiedItem =>
          matchesQuery(item, category.name, query) &&
          matchesFoodFilter(item, foodFilter) &&
          matchesImageFilter(item, imageFilter) &&
          matchesBestsellerFilter(item, bestsellerOnly),
      ),
    }));
  if (selectedCategory !== ALL_CATEGORIES) {
    return matched;
  }
  return matched.filter((category) => category.items.length > 0);
}

export function findItemByKey(categories: IdentifiedCategory[], key: string | null | undefined): IdentifiedItem | null {
  if (!key) {
    return null;
  }
  for (const category of categories) {
    const match = category.items.find((item) => item.key === key);
    if (match) {
      return match;
    }
  }
  return null;
}

export function visibleLabels(labels: string[] | undefined): string[] {
  return (labels || []).map((label) => label.trim()).filter(Boolean);
}

function recordName(value: unknown, keys: string[]): string | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  for (const key of keys) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return null;
}

export function parseMenuGroups(groups: unknown[] | undefined, optionKeys: string[]): MenuGroup[] {
  if (!groups?.length) {
    return [];
  }
  const parsed: MenuGroup[] = [];
  for (const group of groups) {
    if (!group || typeof group !== "object") {
      continue;
    }
    const record = group as Record<string, unknown>;
    const name = recordName(group, ["group_name", "name"]);
    const optionList = optionKeys
      .map((key) => record[key])
      .find((value) => Array.isArray(value)) as unknown[] | undefined;
    const options: MenuGroup["options"] = [];
    for (const option of optionList || []) {
      const optionName = recordName(option, ["name", "title"]);
      if (!optionName) {
        continue;
      }
      const optionRecord = option && typeof option === "object" ? (option as Record<string, unknown>) : {};
      options.push({
        name: optionName,
        price: formatStoredAddonPrice(optionRecord.price),
        amount: addonAmount(optionRecord.price),
        id: String(optionRecord.id ?? optionRecord.groupId ?? optionName),
      });
    }
    if (!name && !options.length) {
      continue;
    }
    parsed.push({ name: name || "Options", options });
  }
  return parsed;
}

export function variantGroups(item: CatalogueItem): MenuGroup[] {
  return parseMenuGroups(item.variants, ["variations", "options", "choices"]);
}

export function customizationGroups(item: CatalogueItem): MenuGroup[] {
  return parseMenuGroups(item.customizations, ["choices", "addonItems", "addons"]);
}

export function itemCount(categories: CatalogueCategory[]): number {
  return categories.reduce((total, category) => total + category.items.length, 0);
}
