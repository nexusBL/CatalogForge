import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getCatalogue, listCatalogues, removeCatalogue, saveCatalogue } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";

const harbor: StoredCatalogue = {
  id: "cat_harbor",
  organizationId: "org_a",
  createdAt: "2026-01-01T00:00:00Z",
  result: {
    extraction_status: "ok",
    restaurant_name: "Harbor Spice House",
    fssai_number: "12345678901234",
    source_url: "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
  },
};

describe("local catalogue store", () => {
  const memory = new Map<string, string>();

  beforeEach(() => {
    memory.clear();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => memory.get(key) ?? null,
        setItem: (key: string, value: string) => {
          memory.set(key, value);
        },
        clear: () => memory.clear(),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps catalogues scoped to the restaurant organization", () => {
    saveCatalogue(harbor);
    expect(listCatalogues("org_a")).toHaveLength(1);
    expect(listCatalogues("org_b")).toHaveLength(0);
    expect(getCatalogue("cat_harbor", "org_a")?.id).toBe("cat_harbor");
    expect(getCatalogue("cat_harbor", "org_b")).toBeUndefined();
  });

  it("deletes only the selected catalogue for that organization", () => {
    const other: StoredCatalogue = {
      ...harbor,
      id: "cat_other",
      organizationId: "org_b",
    };
    saveCatalogue(harbor);
    saveCatalogue(other);
    removeCatalogue("cat_harbor", "org_a");
    expect(getCatalogue("cat_harbor", "org_a")).toBeUndefined();
    expect(getCatalogue("cat_other", "org_b")?.id).toBe("cat_other");
  });

  it("replaces an existing catalogue instead of duplicating it", () => {
    saveCatalogue(harbor);
    saveCatalogue({ ...harbor, createdAt: "2026-02-01T00:00:00Z" });
    expect(listCatalogues("org_a")).toHaveLength(1);
  });
});
