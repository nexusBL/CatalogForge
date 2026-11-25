"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { CatalogueTypeBadge } from "@/components/catalogue-type-badge";
import { DeleteCatalogueButton } from "@/components/delete-catalogue-button";
import { PlatformBadge } from "@/components/platform-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";
import { listCataloguesApi } from "@/lib/catalog-api";
import { listCatalogues } from "@/lib/catalogue-store";
import type { CatalogueType, Platform, StoredCatalogue } from "@/lib/catalog-types";
import { cataloguePlatform } from "@/lib/catalog-types";
import { filterStoredCatalogues } from "@/lib/nav-catalogues";
import { dineoutListMetrics, venueDisplayName, venueLocation } from "@/lib/restaurant-identity";

function readListFilters(): { platform?: Platform; type?: CatalogueType } {
  if (typeof window === "undefined") {
    return {};
  }
  const params = new URLSearchParams(window.location.search);
  const platform = params.get("platform");
  const type = params.get("type");
  return {
    platform: platform === "zomato" || platform === "magicpin" || platform === "swiggy" ? platform : undefined,
    type: type === "dineout" || type === "both" || type === "restaurant" ? type : undefined,
  };
}

export default function CataloguesPage() {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [catalogues, setCatalogues] = useState<StoredCatalogue[]>([]);
  const [filters, setFilters] = useState<{ platform?: Platform; type?: CatalogueType }>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setFilters(readListFilters());
  }, []);

  useEffect(() => {
    if (!organizationId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    listCataloguesApi(organizationId)
      .then((rows) => {
        if (!cancelled) {
          setCatalogues(rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogues(listCatalogues(organizationId));
          setError("Could not refresh catalogues from the API. Showing locally saved results if any.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId]);

  const visible = useMemo(() => filterStoredCatalogues(catalogues, filters), [catalogues, filters]);

  return (
    <DashboardShell title="Catalogues">
      <Container className="space-y-4 py-6">
        {loading ? <p className="text-sm text-muted-foreground">Loading catalogues…</p> : null}
        {error ? <p className="text-sm text-muted-foreground">{error}</p> : null}
        {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
        {!loading && visible.length === 0 ? (
          <p className="text-sm text-muted-foreground">No catalogues generated yet.</p>
        ) : null}
        {visible.map((item) => {
          const location = venueLocation(item.result);
          const metrics = dineoutListMetrics(item.result.dineout);
          const dineoutBits = [
            metrics.photos ? `${metrics.photos} photos` : null,
            metrics.menu ? `${metrics.menu} menu sections` : null,
            metrics.offers ? `${metrics.offers} offers` : null,
          ].filter(Boolean);
          return (
            <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-4">
              <div>
                <p className="font-medium">{venueDisplayName(item.result)}</p>
                {location ? <p className="text-sm text-muted-foreground">{location}</p> : null}
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <PlatformBadge platform={cataloguePlatform(item.result)} />
                  <CatalogueTypeBadge type={item.result.catalogue_type} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {item.result.extraction_status === "ok"
                    ? item.result.catalogue_type === "dineout"
                      ? dineoutBits.join(" · ") || "Ready"
                      : `Categories: ${item.result.categories?.length ?? 0} · Items: ${item.result.item_count ?? 0}`
                    : new Date(item.createdAt).toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground">{new Date(item.createdAt).toLocaleString()}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={item.result.extraction_status} />
                <Button asChild size="sm" variant="outline">
                  <Link href={`/catalogues/${item.id}`}>View</Link>
                </Button>
                {organizationId ? (
                  <DeleteCatalogueButton
                    item={item}
                    organizationId={organizationId}
                    onDeleted={() => {
                      setNotice("Catalogue deleted.");
                      setCatalogues((current) => current.filter((row) => row.id !== item.id));
                    }}
                  />
                ) : null}
              </div>
            </div>
          );
        })}
      </Container>
    </DashboardShell>
  );
}
