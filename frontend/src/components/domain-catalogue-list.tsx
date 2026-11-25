"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
import type { StoredCatalogue } from "@/lib/catalog-types";
import { cataloguePlatform } from "@/lib/catalog-types";
import {
  catalogueMatchesDomain,
  dineoutListMetrics,
  restaurantDisplayName,
  venueDisplayName,
  venueLocation,
} from "@/lib/restaurant-identity";

export function DomainCatalogueList({
  title,
  domain,
  empty,
}: {
  title: string;
  domain: "restaurant" | "dineout";
  empty: string;
}) {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [catalogues, setCatalogues] = useState<StoredCatalogue[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    listCataloguesApi(organizationId)
      .then((rows) => {
        if (!cancelled) {
          setCatalogues(rows.filter((row) => catalogueMatchesDomain(row.result, domain)));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogues(listCatalogues(organizationId).filter((row) => catalogueMatchesDomain(row.result, domain)));
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
  }, [organizationId, domain]);

  const latest = catalogues[0];
  const contextName = latest
    ? domain === "dineout"
      ? venueDisplayName(latest.result)
      : restaurantDisplayName(latest.result.restaurant, latest.result.restaurant_name)
    : null;
  const contextLocation = latest ? venueLocation(latest.result) : null;

  return (
    <DashboardShell title={title}>
      <Container className="space-y-6 py-6">
        {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
        {latest ? (
          <div className="rounded-2xl border border-border bg-card p-6">
            {contextName ? <p className="text-xl font-medium">{contextName}</p> : null}
            {contextLocation ? <p className="text-sm text-muted-foreground">{contextLocation}</p> : null}
            {latest.result.restaurant?.address && latest.result.restaurant.address !== contextLocation ? (
              <p className="mt-1 text-sm text-muted-foreground">{latest.result.restaurant.address}</p>
            ) : null}
            <p className="mt-3 text-sm text-muted-foreground">
              {catalogues.length} catalogue{catalogues.length === 1 ? "" : "s"}
            </p>
          </div>
        ) : null}
        {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
        {!loading && catalogues.length === 0 ? (
          <div className="rounded-2xl border border-border bg-card p-8">
            <p className="text-sm text-muted-foreground">{empty}</p>
            <Button asChild className="mt-4">
              <Link href="/catalogues/new">Create Catalogue</Link>
            </Button>
          </div>
        ) : null}
        {catalogues.map((item) => {
          const name = venueDisplayName(item.result);
          const location = venueLocation(item.result);
          const metrics = dineoutListMetrics(item.result.dineout);
          const dineoutSummary = [
            metrics.rating != null ? `★ ${metrics.rating}` : null,
            metrics.photos ? `${metrics.photos} photos` : null,
            metrics.menu ? `${metrics.menu} menu sections` : null,
            metrics.offers ? `${metrics.offers} offers` : null,
          ]
            .filter(Boolean)
            .join(" · ");
          return (
            <div key={item.id} className="rounded-lg border border-border p-4">
              <p className="font-medium">{name}</p>
              {location ? <p className="text-sm text-muted-foreground">{location}</p> : null}
              <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <PlatformBadge platform={cataloguePlatform(item.result)} />
                  <CatalogueTypeBadge type={item.result.catalogue_type} />
              <p className="text-sm text-muted-foreground">
                {item.result.extraction_status === "ok"
                  ? domain === "dineout"
                    ? dineoutSummary || "Ready"
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
            </div>
          );
        })}
      </Container>
    </DashboardShell>
  );
}
