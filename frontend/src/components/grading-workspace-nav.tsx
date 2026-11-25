"use client";

import Link from "next/link";
import { gradingWorkspaceHref, type GradingWorkspaceTab } from "@/lib/grading-ui";
import { catalogueImprovementsHref } from "@/lib/improvement-ui";
import { catalogueReviewsHref } from "@/lib/review-ui";
import { cn } from "@/lib/utils";

export function GradingWorkspaceNav({
  catalogueId,
  active,
}: {
  catalogueId: string;
  active: GradingWorkspaceTab | "improvements" | "reviews";
}) {
  const items: Array<{ id: GradingWorkspaceTab | "improvements" | "reviews"; label: string; href: string }> = [
    { id: "quality", label: "Quality", href: gradingWorkspaceHref(catalogueId) },
    { id: "photos", label: "Photos", href: gradingWorkspaceHref(catalogueId, "photos") },
    { id: "video", label: "Video", href: gradingWorkspaceHref(catalogueId, "video") },
    { id: "improvements", label: "AI Improvements", href: catalogueImprovementsHref(catalogueId) },
    { id: "reviews", label: "Reviews", href: catalogueReviewsHref(catalogueId) },
  ];
  return (
    <nav className="flex flex-wrap gap-2" aria-label="Grading workspace">
      {items.map((item) => (
        <Link
          key={item.id}
          href={item.href}
          aria-current={active === item.id ? "page" : undefined}
          className={cn(
            "rounded-md border px-3 py-1.5 text-sm transition-colors",
            active === item.id
              ? "border-border bg-selected text-foreground"
              : "border-border bg-background text-muted-foreground hover:bg-selected",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
