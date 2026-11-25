import { afterEach, describe, expect, it, vi } from "vitest";
import { createCatalogue } from "@/lib/catalog-api";

describe("catalogue API request", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to the CatalogForge API proxy", async function () {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        extraction_status: "ok",
        restaurant_name: "Harbor Spice House",
        fssai_number: "123",
        source_url: "https://www.swiggy.com/city/x/y-rest1",
        restaurant: { name: "Harbor Spice House" },
        categories: [],
        item_count: 0,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await createCatalogue({
      restaurant_name: "Harbor Spice House",
      fssai_number: "12345678901234",
      swiggy_url: "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
      organization_id: "org_1",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalog/create",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(result.extraction_status).toBe("ok");
  });

  it("lists catalogues for an organization", async function () {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        catalogues: [
          {
            id: "cat_1",
            organization_id: "org_1",
            created_at: "2026-01-01T00:00:00Z",
            result: {
              extraction_status: "ok",
              restaurant_name: "Harbor Spice House",
              fssai_number: "123",
              source_url: "https://www.swiggy.com/city/x/y-rest1",
            },
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { listCataloguesApi } = await import("@/lib/catalog-api");
    const rows = await listCataloguesApi("org_1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalogues?organization_id=org_1",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(rows[0].organizationId).toBe("org_1");
    expect(rows[0].id).toBe("cat_1");
  });

  it("posts an assistant turn through the catalogue proxy", async function () {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        message: "Your catalogue is graded C.",
        intent: "explain_catalogue_grade",
        used_llm: false,
        actions: [{ label: "View Grade Details", href: "/catalogues/cat_1" }],
        unavailable: null,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { assistantTurnApi } = await import("@/lib/catalog-api");
    const row = await assistantTurnApi("cat_1", "org_1", "Why did I get a C?");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalogues/cat_1/assistant/turn?organization_id=org_1",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(row.intent).toBe("explain_catalogue_grade");
    expect(row.actions[0].href).toBe("/catalogues/cat_1");
  });

  it("posts mutation confirm through the catalogue proxy", async function () {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        message: "Done. Ghee Rice was updated.",
        intent: "propose_mutation",
        used_llm: false,
        actions: [],
        unavailable: null,
        proposal: { proposal_id: "p1", status: "APPLIED", confirm_token: null },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { confirmMutationApi } = await import("@/lib/catalog-api");
    const row = await confirmMutationApi("cat_1", "org_1", "p1", "token-token");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalogues/cat_1/assistant/mutations/p1/confirm?organization_id=org_1",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(row.intent).toBe("propose_mutation");
  });

  it("returns null when a catalogue is not in the organization", async function () {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }),
    );
    const { getCatalogueApi } = await import("@/lib/catalog-api");
    await expect(getCatalogueApi("missing", "org_1")).resolves.toBeNull();
  });

  it("deletes a catalogue through the API proxy", async function () {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true, id: "cat_1" }) });
    vi.stubGlobal("fetch", fetchMock);
    const { deleteCatalogueApi } = await import("@/lib/catalog-api");
    await deleteCatalogueApi("cat_1", "org_1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalogues/cat_1?organization_id=org_1",
      expect.objectContaining({ method: "DELETE", credentials: "include" }),
    );
  });

  it("deletes a discovery job through the API proxy", async function () {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true, id: "job_1" }) });
    vi.stubGlobal("fetch", fetchMock);
    const { deleteAreaJobApi } = await import("@/lib/catalog-api");
    await deleteAreaJobApi("job_1", "org_1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/area-jobs/job_1?organization_id=org_1",
      expect.objectContaining({ method: "DELETE", credentials: "include" }),
    );
  });

  it("loads a grade explanation through the API proxy", async function () {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        catalogue_id: "cat_1",
        overall_grade: "B",
        findings: [],
        recommendations: [],
        derived: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { getGradeExplanationApi } = await import("@/lib/catalog-api");
    const row = await getGradeExplanationApi("cat_1", "org_1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalogues/cat_1/grade-explanation?organization_id=org_1",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(row?.overall_grade).toBe("B");
  });

  it("posts an improvement preview request without an apply endpoint", async function () {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "p1",
        status: "READY",
        lines: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { createImprovementApi } = await import("@/lib/catalog-api");
    await createImprovementApi("cat_1", "org_1", { check_id: "missing_description" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalogues/cat_1/improvements?organization_id=org_1",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("apply");
  });

  it("maps unauthenticated responses", async function () {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) }),
    );
    await expect(
      createCatalogue({
        restaurant_name: "Harbor Spice House",
        fssai_number: "12345678901234",
        swiggy_url: "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
        organization_id: "org_1",
      }),
    ).rejects.toMatchObject({
      message: "You need to sign in before using catalogues.",
      status: 401,
    });
  });

  it("retries once after a network failure", async function () {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ catalogues: [] }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const { listCataloguesApi } = await import("@/lib/catalog-api");
    const promise = listCataloguesApi("org_1");
    await vi.advanceTimersByTimeAsync(5000);
    await promise;
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
