"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import MetricCard from "@/components/metric-card";
import { OverviewCatalogueCard } from "@/components/overview-catalogue-card";
import { CatalogueImage } from "@/components/catalogue-image";
import { Button } from "@/components/ui/button";
import { CatalogueTypeBadge } from "@/components/catalogue-type-badge";
import { PlatformBadge } from "@/components/platform-badge";
import { StatusBadge } from "@/components/status-badge";
import { cataloguePlatform } from "@/lib/catalog-types";
import { authClient } from "@/lib/auth-client";
import { listCataloguesApi } from "@/lib/catalog-api";
import { listCatalogues } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import {
  catalogueType,
  dineoutListMetrics,
  overviewStats,
  venueDisplayName,
  venueLocation,
} from "@/lib/restaurant-identity";

export default function OverviewPage() {
  const { data: organizations } = authClient.useListOrganizations();
  const restaurant = organizations?.[0];
  const [catalogues, setCatalogues] = useState<StoredCatalogue[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!restaurant?.id) {
      return;
    }
    listCataloguesApi(restaurant.id)
      .then(setCatalogues)
      .catch(() => setCatalogues(listCatalogues(restaurant.id)));
  }, [restaurant?.id]);

  const stats = useMemo(() => overviewStats(catalogues), [catalogues]);
  const latestRestaurant = catalogues.find((item) => {
    const type = catalogueType(item.result.catalogue_type);
    return type === "restaurant" || type === "both";
  });
  const latestDineout = catalogues.find((item) => {
    const type = catalogueType(item.result.catalogue_type);
    return type === "dineout" || type === "both";
  });

  return (
    <DashboardShell title="Overview">
        <div className="grid grid-cols-2 border-b border-border laptop:grid-cols-4">
        <Container className="border-b border-border py-4 laptop:border-b-0 laptop:border-r">
          <MetricCard title="Total Catalogues" value={String(stats.total)} />
        </Container>
        <Container className="border-b border-border py-4 laptop:border-b-0 laptop:border-r">
          <MetricCard title="Restaurant" value={String(stats.restaurant)} />
        </Container>
        <Container className="border-b border-border py-4 laptop:border-r">
          <MetricCard title="Dineout" value={String(stats.dineout)} />
        </Container>
        <Container className="py-4">
          <MetricCard title="Both" value={String(stats.both)} />
        </Container>
      </div>
      <div className="grid grid-cols-3 border-b border-border">
        <Container className="border-r border-border py-4">
          <MetricCard title="Swiggy" value={String(stats.swiggy)} />
        </Container>
        <Container className="border-r border-border py-4">
          <MetricCard title="Zomato" value={String(stats.zomato)} />
        </Container>
        <Container className="py-4">
          <MetricCard title="Magicpin" value={String(stats.magicpin)} />
        </Container>
      </div>
      {(stats.items > 0 || stats.images > 0) && stats.total > 0 ? (
        <div className="grid grid-cols-2 border-b border-border">
          <Container className="border-r border-border py-4">
            <MetricCard title="Total Items" value={String(stats.items)} />
          </Container>
          <Container className="py-4">
            <MetricCard title="Total Images" value={String(stats.images)} />
          </Container>
        </div>
      ) : null}
      <Container className="space-y-8 py-6">
        {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Overview</h2>
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/catalogues/new">Create Catalogue</Link>
            </Button>
            {catalogues.length ? (
              <Button asChild variant="outline">
                <Link href="/catalogues">View Catalogues</Link>
              </Button>
            ) : null}
          </div>
        </div>
        {catalogues.length === 0 ? (
          <div className="rounded-2xl border border-border bg-card p-8 text-center">
            <p className="text-lg font-medium">No catalogues yet</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Create your first Restaurant or Dineout catalogue.
            </p>
            <Button asChild className="mt-6">
              <Link href="/catalogues/new">Create Catalogue</Link>
            </Button>
          </div>
        ) : (
          <>
            <section className="space-y-3">
              <h3 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Restaurant</h3>
              <p className="text-sm text-muted-foreground">
                {stats.restaurant + stats.both} restaurant catalogue
                {stats.restaurant + stats.both === 1 ? "" : "s"}
              </p>
              {latestRestaurant ? <LatestRestaurantCard item={latestRestaurant} /> : null}
            </section>
            <section className="space-y-3">
              <h3 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Dineout</h3>
              <p className="text-sm text-muted-foreground">
                {stats.dineout + stats.both} dineout catalogue
                {stats.dineout + stats.both === 1 ? "" : "s"}
              </p>
              {latestDineout ? <LatestDineoutCard item={latestDineout} /> : null}
            </section>
            <section className="space-y-3">
              <h3 className="text-lg font-medium">Recent catalogues</h3>
              <div className="space-y-3">
                {catalogues.slice(0, 8).map((item) => (
                  <OverviewCatalogueCard
                    key={item.id}
                    item={item}
                    organizationId={restaurant?.id}
                    onDeleted={() => {
                      setNotice("Catalogue deleted.");
                      setCatalogues((current) => current.filter((row) => row.id !== item.id));
                    }}
                  />
                ))}
              </div>
            </section>
          </>
        )}
      </Container>
    </DashboardShell>
  );
}

function LatestRestaurantCard({ item }: { item: StoredCatalogue }) {
  const location = venueLocation(item.result);
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="font-medium">{venueDisplayName(item.result)}</p>
      {location ? <p className="text-sm text-muted-foreground">{location}</p> : null}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <PlatformBadge platform={cataloguePlatform(item.result)} />
        <CatalogueTypeBadge type={item.result.catalogue_type} />
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        {item.result.item_count ?? 0} items · {item.result.image_count ?? 0} images
      </p>
      <p className="text-xs text-muted-foreground">Last generated {new Date(item.createdAt).toLocaleString()}</p>
    </div>
  );
}

function LatestDineoutCard({ item }: { item: StoredCatalogue }) {
  const venue = item.result.dineout;
  const metrics = dineoutListMetrics(venue);
  const location = venueLocation(item.result);
  const hero = venue?.hero_image;
  return (
    <div className="flex gap-4 rounded-xl border border-border bg-card p-4">
      {hero ? (
        <CatalogueImage src={hero} alt="" className="size-24 shrink-0 rounded-lg object-cover" />
      ) : null}
      <div className="min-w-0 space-y-1">
        <p className="font-medium">{venueDisplayName(item.result)}</p>
        {location ? <p className="text-sm text-muted-foreground">{location}</p> : null}
        <p className="text-sm text-muted-foreground">
          {[
            metrics.rating != null ? `★ ${metrics.rating}` : null,
            metrics.photos ? `${metrics.photos} photos` : null,
            metrics.menu ? `${metrics.menu} menu sections` : null,
            metrics.offers ? `${metrics.offers} offers` : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <div className="flex items-center gap-2 pt-1">
          <PlatformBadge platform={cataloguePlatform(item.result)} />
          <CatalogueTypeBadge type={item.result.catalogue_type} />
          <StatusBadge status={item.result.extraction_status} />
        </div>
      </div>
    </div>
  );
}
