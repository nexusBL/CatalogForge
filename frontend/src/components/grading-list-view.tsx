"use client";

import Link from "next/link";
import { CatalogueImage } from "@/components/catalogue-image";
import { letterBadgeClass } from "@/lib/grade-ui";
import {
  GRADE_FILTER_LETTERS,
  gradingWorkspaceHref,
  type GradeListFilter,
  type GradingListRow,
  type VenueDomainFilter,
} from "@/lib/grading-ui";
import { cn } from "@/lib/utils";

export function GradingListView({
  rows,
  domain,
  grade,
  onDomain,
  onGrade,
}: {
  rows: GradingListRow[];
  domain: VenueDomainFilter;
  grade: GradeListFilter;
  onDomain: (value: VenueDomainFilter) => void;
  onGrade: (value: GradeListFilter) => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Overall Baba grades for your restaurants and dineouts. Open a row to review quality, photos, and video tools.
      </p>
      <div className="flex flex-wrap gap-2" aria-label="Venue type">
        {(["all", "restaurant", "dineout"] as VenueDomainFilter[]).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onDomain(value)}
            className={cn(
              "rounded-md border px-3 py-1.5 text-sm",
              domain === value
                ? "border-border bg-selected text-foreground"
                : "border-border bg-background text-muted-foreground hover:bg-selected",
            )}
          >
            {value === "all" ? "All venues" : value === "dineout" ? "Dineout" : "Restaurant"}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2" aria-label="Overall grade">
        <button
          type="button"
          onClick={() => onGrade("all")}
          className={cn(
            "rounded-md border px-3 py-1.5 text-sm",
            grade === "all"
              ? "border-border bg-selected text-foreground"
              : "border-border bg-background text-muted-foreground hover:bg-selected",
          )}
        >
          All grades
        </button>
        {GRADE_FILTER_LETTERS.map((letter) => (
          <button
            key={letter}
            type="button"
            onClick={() => onGrade(letter)}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium",
              grade === letter ? letterBadgeClass(letter) : "border border-border text-muted-foreground",
            )}
          >
            {letter}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onGrade("ungraded")}
          className={cn(
            "rounded-md border px-3 py-1.5 text-sm",
            grade === "ungraded"
              ? "border-border bg-selected text-foreground"
              : "border-border bg-background text-muted-foreground hover:bg-selected",
          )}
        >
          Not graded
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No restaurants or dineouts match this filter.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Venue</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Platform</th>
                <th className="px-3 py-2 font-medium">Location</th>
                <th className="px-3 py-2 font-medium">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2">
                    <Link href={gradingWorkspaceHref(row.id)} className="flex items-center gap-3 hover:underline">
                      <CatalogueImage
                        src={row.thumbnail}
                        alt=""
                        className="h-12 w-12 rounded-md object-cover"
                        fallbackClassName="h-12 w-12 rounded-md"
                      />
                      <span className="font-medium">{row.name}</span>
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{row.typeLabel}</td>
                  <td className="px-3 py-2 text-muted-foreground">{row.platformLabel}</td>
                  <td className="px-3 py-2 text-muted-foreground">{row.location || "—"}</td>
                  <td className="px-3 py-2">
                    {row.letter ? (
                      <span
                        className={cn(
                          "inline-flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold",
                          letterBadgeClass(row.letter),
                        )}
                      >
                        {row.letter}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Not graded</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
