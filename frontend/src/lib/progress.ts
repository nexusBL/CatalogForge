import type { AreaJob } from "@/lib/area-jobs";
import { scrapeProgress } from "@/lib/area-jobs";

export type ProcessPhase = "idle" | "running" | "completed" | "failed";

export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function scrapePercent(job: AreaJob): number {
  const { current, total } = scrapeProgress(job);
  if (!total) {
    if (job.status === "scraping" || job.status === "queued") {
      return 5;
    }
    return 0;
  }
  if (job.status === "completed" || job.status === "partially_completed") {
    return 100;
  }
  return clampPercent((current / total) * 100);
}

export function scrapePhase(job: AreaJob): ProcessPhase {
  if (job.status === "scraping" || job.status === "queued") {
    return "running";
  }
  if (job.status === "completed") {
    return "completed";
  }
  if (job.status === "partially_completed") {
    return "completed";
  }
  if (job.status === "failed") {
    return "failed";
  }
  return "idle";
}

export function indeterminatePercent(tick: number, cap = 95): number {
  if (tick < 10) {
    return clampPercent(8 + tick * 8); // 8% up to 80% quickly in ~9s
  }
  // Asymptotically creep from 80% towards 98% so users know progress is still alive
  return clampPercent(Math.min(cap, 80 + Math.floor(Math.log2(tick - 8) * 4)));
}
