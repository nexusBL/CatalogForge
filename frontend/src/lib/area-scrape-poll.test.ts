import { describe, expect, it } from "vitest";
import { claimScrapeTick, releaseScrapeTick } from "@/lib/area-scrape-poll";

describe("area scrape-batch single-flight", () => {
  it("skips a tick while a previous scrape-batch request is pending", async () => {
    const inFlight = { current: false };
    let started = 0;
    let finished = 0;
    let resolveFirst: () => void = () => undefined;
    const firstGate = new Promise<void>((resolve) => {
      resolveFirst = resolve;
    });

    async function tick() {
      if (!claimScrapeTick(inFlight)) {
        return;
      }
      started += 1;
      try {
        if (started === 1) {
          await firstGate;
        }
      } finally {
        releaseScrapeTick(inFlight);
        finished += 1;
      }
    }

    const first = tick();
    await tick();
    await tick();
    expect(started).toBe(1);
    expect(finished).toBe(0);
    resolveFirst();
    await first;
    expect(finished).toBe(1);
    await tick();
    expect(started).toBe(2);
    expect(finished).toBe(2);
  });
});
