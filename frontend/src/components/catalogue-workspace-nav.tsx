"use client";

import Link from "next/link";
import { catalogueManageHref } from "@/lib/manage-catalogue-ui";
import { catalogueImprovementsHref } from "@/lib/improvement-ui";
import { catalogueMediaHref } from "@/lib/media-ui";
import { catalogueReviewsHref } from "@/lib/review-ui";
import { cn } from "@/lib/utils";

export function CatalogueWorkspaceNav({
  catalogueId,
  active,
}: {
  catalogueId: string;
  active: "catalogue" | "manage" | "grade" | "improvements" | "media" | "reviews";
}) {
  return (
    <nav className="flex flex-wrap gap-2" aria-label="Catalogue workspace">
      <Link
        href={`/catalogues/${catalogueId}`}
        aria-current={active === "catalogue" ? "page" : undefined}
        className={cn(
          "rounded-md border px-3 py-1.5 text-sm transition-colors",
          active === "catalogue"
            ? "border-border bg-selected text-foreground"
            : "border-border bg-background text-muted-foreground hover:bg-selected",
        )}
      >
        Catalogue
      </Link>
      <Link
        href={catalogueManageHref(catalogueId)}
        aria-current={active === "manage" ? "page" : undefined}
        className={cn(
          "rounded-md border px-3 py-1.5 text-sm transition-colors",
          active === "manage"
            ? "border-border bg-selected text-foreground"
            : "border-border bg-background text-muted-foreground hover:bg-selected",
        )}
      >
        Manage Catalogue
      </Link>
      <Link
        href={catalogueImprovementsHref(catalogueId)}
        aria-current={active === "improvements" || active === "grade" ? "page" : undefined}

        className={cn(
          "rounded-md border px-3 py-1.5 text-sm transition-colors",
          active === "improvements" || active === "grade"
            ? "border-border bg-selected text-foreground"
            : "border-border bg-background text-muted-foreground hover:bg-selected",
        )}
      >
        Grade / AI Improvements
      </Link>
      <Link
        href={catalogueMediaHref(catalogueId)}
        aria-current={active === "media" ? "page" : undefined}
        className={cn(
          "rounded-md border px-3 py-1.5 text-sm transition-colors",
          active === "media"
            ? "border-border bg-selected text-foreground"
            : "border-border bg-background text-muted-foreground hover:bg-selected",
        )}
      >
        Generated Media
      </Link>
      <Link
        href={catalogueReviewsHref(catalogueId)}
        aria-current={active === "reviews" ? "page" : undefined}
        className={cn(
          "rounded-md border px-3 py-1.5 text-sm transition-colors",
          active === "reviews"
            ? "border-border bg-selected text-foreground"
            : "border-border bg-background text-muted-foreground hover:bg-selected",
        )}
      >
        Reviews
      </Link>
    </nav>
  );
}
