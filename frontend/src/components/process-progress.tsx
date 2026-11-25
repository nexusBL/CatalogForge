"use client";

import type { ProcessPhase } from "@/lib/progress";
import { clampPercent } from "@/lib/progress";
import { cn } from "@/lib/utils";

export function ProcessProgressBar({
  phase,
  percent,
  runningLabel = "Scraping…",
  completedLabel = "Completed",
  failedLabel = "Failed",
  className,
}: {
  phase: Exclude<ProcessPhase, "idle">;
  percent: number;
  runningLabel?: string;
  completedLabel?: string;
  failedLabel?: string;
  className?: string;
}) {
  const safe = clampPercent(percent);
  const displayPercent = phase === "completed" ? 100 : safe;
  const barWidth =
    phase === "completed"
      ? 100
      : phase === "failed"
        ? Math.max(displayPercent, 100)
        : Math.max(displayPercent, phase === "running" && displayPercent < 5 ? 10 : displayPercent);

  const label =
    phase === "completed" ? completedLabel : phase === "failed" ? failedLabel : runningLabel;

  return (
    <div
      className={cn("space-y-2 rounded-xl border border-border bg-card p-4", className)}
      role="status"
      aria-live="polite"
      aria-busy={phase === "running"}
    >
      <div className="flex items-center justify-between gap-3 text-sm">
        <div className="flex items-center gap-2 font-medium">
          {phase === "running" ? (
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-foreground border-t-transparent" />
          ) : null}
          <p>{label}</p>
        </div>
        <span className="tabular-nums text-muted-foreground">{displayPercent}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 ease-out",
            phase === "completed" && "bg-emerald-600",
            phase === "failed" && "bg-destructive",
            phase === "running" &&
              "bg-[length:30px_30px] bg-[linear-gradient(45deg,rgba(255,255,255,0.25)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.25)_50%,rgba(255,255,255,0.25)_75%,transparent_75%,transparent)] bg-foreground animate-stripe",
          )}
          style={{ width: `${barWidth}%` }}
        />
      </div>
    </div>
  );
}
