"use client";

import Link from "next/link";
import { CatalogueTypeBadge } from "@/components/catalogue-type-badge";
import { DeleteCatalogueButton } from "@/components/delete-catalogue-button";
import { PlatformBadge } from "@/components/platform-badge";
import { StatusBadge } from "@/components/status-badge";
import type { StoredCatalogue } from "@/lib/catalog-types";
import { cataloguePlatform } from "@/lib/catalog-types";
import { catalogueType, dineoutListMetrics, venueDisplayName, venueLocation } from "@/lib/restaurant-identity";

export function OverviewCatalogueCard({
  item,
  organizationId,
  onDeleted,
}: {
  item: StoredCatalogue;
  organizationId?: string;
  onDeleted?: () => void;
}) {
  const type = catalogueType(item.result.catalogue_type);
  const dineout = item.result.dineout;
  const metrics = dineoutListMetrics(dineout);
  const location = venueLocation(item.result);
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="font-medium">{venueDisplayName(item.result)}</p>
          {location ? <p className="text-sm text-muted-foreground">{location}</p> : null}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <PlatformBadge platform={cataloguePlatform(item.result)} />
            <CatalogueTypeBadge type={item.result.catalogue_type} />
            <StatusBadge status={item.result.extraction_status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {type === "dineout"
              ? [
                  metrics.rating != null ? `${metrics.rating} ★${metrics.ratingCount ? ` · ${metrics.ratingCount} ratings` : ""}` : null,
                  metrics.photos ? `Photos: ${metrics.photos}` : null,
                  metrics.menu ? `Menu sections: ${metrics.menu}` : null,
                  metrics.offers ? `Offers: ${metrics.offers}` : null,
                ]
                  .filter(Boolean)
                  .join(" · ") || new Date(item.createdAt).toLocaleString()
              : `${item.result.item_count ?? 0} items · ${item.result.image_count ?? 0} images`}
          </p>
          <p className="text-xs text-muted-foreground">{new Date(item.createdAt).toLocaleString()}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/catalogues/${item.id}`} className="text-sm font-medium hover:underline">
            View Catalogue
          </Link>
          {organizationId ? (
            <DeleteCatalogueButton item={item} organizationId={organizationId} onDeleted={onDeleted} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
