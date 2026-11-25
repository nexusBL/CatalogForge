import { describe, expect, it } from "vitest";
import type { AreaJob } from "@/lib/area-jobs";
import { clampPercent, indeterminatePercent, scrapePercent, scrapePhase } from "@/lib/progress";

function job(partial: Partial<AreaJob>): AreaJob {
  return {
    id: "job_1",
    organization_id: "org_1",
    location: { original: "JP Nagar" },
    platforms: ["swiggy"],
    catalogue_type: "restaurant",
    status: "scraping",
    venues: [],
    ...partial,
  };
}

describe("progress helpers", () => {
  it("clamps percent values", () => {
    expect(clampPercent(-5)).toBe(0);
    expect(clampPercent(42.6)).toBe(43);
    expect(clampPercent(140)).toBe(100);
  });

  it("returns scrape phase from job status", () => {
    expect(scrapePhase(job({ status: "scraping" }))).toBe("running");
    expect(scrapePhase(job({ status: "completed" }))).toBe("completed");
    expect(scrapePhase(job({ status: "partially_completed" }))).toBe("completed");
    expect(scrapePhase(job({ status: "failed" }))).toBe("failed");
    expect(scrapePhase(job({ status: "awaiting_confirmation" }))).toBe("idle");
  });

  it("computes scrape percent from completed counts", () => {
    expect(
      scrapePercent(
        job({
          status: "scraping",
          selected_count: 4,
          completed_count: 2,
        }),
      ),
    ).toBe(50);
    expect(scrapePercent(job({ status: "completed", selected_count: 10, completed_count: 10 }))).toBe(100);
  });

  it("ramps indeterminate percent for long-running requests", () => {
    expect(indeterminatePercent(0)).toBe(8);
    expect(indeterminatePercent(3)).toBe(32);
    expect(indeterminatePercent(20)).toBe(94);
  });
});
