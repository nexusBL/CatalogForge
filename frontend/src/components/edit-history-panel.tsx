"use client";

import { Button } from "@/components/ui/button";
import type { EditHistoryRecord } from "@/lib/history-types";

function displayValue(value: unknown): string {
  if (value == null || value === "") {
    return "(empty)";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function EditHistoryPanel({
  records,
  rollingBackId = null,
  onRollback,
}: {
  records: EditHistoryRecord[];
  rollingBackId?: string | null;
  onRollback: (record: EditHistoryRecord) => void;
}) {
  return (
    <section className="space-y-3 rounded-xl border border-border bg-card p-5 text-card-foreground">
      <div>
        <h2 className="text-base font-semibold">Edit history</h2>
        <p className="text-sm text-muted-foreground">
          Approved catalogue changes are recorded here. Rollback restores the previous value and keeps the original history row.
        </p>
      </div>
      {records.length === 0 ? (
        <p className="text-sm text-muted-foreground">No approved catalogue edits yet.</p>
      ) : (
        <ul className="space-y-3">
          {records.map((record) => (
            <li key={record.id} className="rounded-lg border border-border p-3 text-sm">
              <p className="font-medium">
                {record.item_name || record.path || record.operation} · {record.source}
              </p>
              <p className="mt-1 text-muted-foreground">
                {displayValue(record.previous_value)} → {displayValue(record.new_value)}
              </p>
              {record.after_grade_letter ? (
                <p className="mt-1">
                  Grade {record.before_grade_letter ?? "—"} → {record.after_grade_letter}
                  {record.overall_score_delta != null
                    ? ` (${record.overall_score_delta > 0 ? "+" : ""}${record.overall_score_delta})`
                    : ""}
                </p>
              ) : null}
              {record.resolved_issue_ids.length ? (
                <p className="mt-1 text-muted-foreground">Resolved: {record.resolved_issue_ids.join(", ")}</p>
              ) : null}
              {record.source !== "rollback" ? (
                <Button
                  className="mt-2"
                  variant="outline"
                  disabled={rollingBackId === record.id}
                  onClick={() => {
                    if (
                      globalThis.confirm(
                        "Roll back this approved catalogue change? The original history row will be kept.",
                      )
                    ) {
                      onRollback(record);
                    }
                  }}
                >
                  {rollingBackId === record.id ? "Rolling back…" : "Roll back"}
                </Button>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">
                  Rollback of {record.rolled_back_history_id}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
