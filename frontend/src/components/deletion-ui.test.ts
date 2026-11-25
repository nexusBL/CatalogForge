import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CATALOGUE_PERMANENT_DELETE_CONFIRM, DISCOVERY_JOB_DELETE_CONFIRM } from "@/lib/area-jobs";

const here = dirname(fileURLToPath(import.meta.url));

describe("deletion confirmation copy", () => {
  it("keeps discovery-job and catalogue delete dialogs distinct", () => {
    const jobButton = readFileSync(join(here, "delete-discovery-job-button.tsx"), "utf8");
    const catalogueButton = readFileSync(join(here, "delete-catalogue-button.tsx"), "utf8");
    const areas = readFileSync(join(here, "../app/(dashboard)/areas/page.tsx"), "utf8");
    expect(jobButton).toContain("DISCOVERY_JOB_DELETE_CONFIRM");
    expect(DISCOVERY_JOB_DELETE_CONFIRM).toBe("Delete this discovery job permanently?");
    expect(jobButton).toContain("Existing catalogues created from selected venues are not deleted");
    expect(catalogueButton).toContain("CATALOGUE_PERMANENT_DELETE_CONFIRM");
    expect(CATALOGUE_PERMANENT_DELETE_CONFIRM).toContain("cannot be undone");
    expect(catalogueButton).toContain("Delete this catalogue permanently?");
    expect(catalogueButton).toContain("Delete permanently");
    expect(areas).toContain("Failed");
    expect(areas).toContain("DeleteDiscoveryJobButton");
  });
});
