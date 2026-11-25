"use client";

import { useEffect, useState } from "react";
import { DineoutAboutFields } from "@/components/about-fields";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { authClient } from "@/lib/auth-client";
import { listCataloguesApi } from "@/lib/catalog-api";
import { listCatalogues } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import { catalogueMatchesDomain, resolveDineout } from "@/lib/restaurant-identity";

export default function DineoutAboutPage() {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [latest, setLatest] = useState<StoredCatalogue | null>(null);

  useEffect(() => {
    if (!organizationId) {
      return;
    }
    listCataloguesApi(organizationId)
      .then((rows) => setLatest(rows.find((row) => catalogueMatchesDomain(row.result, "dineout")) ?? null))
      .catch(() => {
        setLatest(listCatalogues(organizationId).find((row) => catalogueMatchesDomain(row.result, "dineout")) ?? null);
      });
  }, [organizationId]);

  return (
    <DashboardShell title="Dineout About">
      <Container className="space-y-4 py-6">
        <DineoutAboutFields venue={latest ? resolveDineout(latest.result) : null} fallbackUrl={latest?.result.source_url} />
      </Container>
    </DashboardShell>
  );
}
