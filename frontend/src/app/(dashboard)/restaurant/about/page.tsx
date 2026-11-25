"use client";

import { useEffect, useState } from "react";
import { AboutFields } from "@/components/about-fields";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { authClient } from "@/lib/auth-client";
import { listCataloguesApi } from "@/lib/catalog-api";
import { listCatalogues } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import { catalogueMatchesDomain } from "@/lib/restaurant-identity";

export default function RestaurantAboutPage() {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [latest, setLatest] = useState<StoredCatalogue | null>(null);

  useEffect(() => {
    if (!organizationId) {
      return;
    }
    listCataloguesApi(organizationId)
      .then((rows) => setLatest(rows.find((row) => catalogueMatchesDomain(row.result, "restaurant")) ?? null))
      .catch(() => {
        setLatest(listCatalogues(organizationId).find((row) => catalogueMatchesDomain(row.result, "restaurant")) ?? null);
      });
  }, [organizationId]);

  return (
    <DashboardShell title="Restaurant About">
      <Container className="space-y-4 py-6">
        <AboutFields
          restaurant={latest?.result.restaurant}
          restaurantName={latest?.result.restaurant_name}
          fssaiNumber={latest?.result.fssai_number}
          sourceUrl={latest?.result.source_url}
        />
      </Container>
    </DashboardShell>
  );
}
