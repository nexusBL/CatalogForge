import { cn } from "@/lib/utils";
import type { ExtractionStatus } from "@/lib/catalog-types";

const LABELS: Record<ExtractionStatus, string> = {
  ok: "Ready",
  partial: "Partial",
  blocked: "Blocked",
  failed: "Failed",
  pending: "Pending",
};

export function StatusBadge({ status }: { status: ExtractionStatus }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
        status === "ok" && "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300",
        status === "partial" && "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
        status === "blocked" && "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
        status === "failed" && "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
        status === "pending" && "bg-muted text-muted-foreground",
      )}
    >
      {LABELS[status]}
    </span>
  );
}
