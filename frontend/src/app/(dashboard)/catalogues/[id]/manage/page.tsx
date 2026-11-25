"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CatalogueLoading } from "@/components/catalogue-view";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { ManageCatalogueView } from "@/components/manage-catalogue-view";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { authClient } from "@/lib/auth-client";
import { getCatalogueApi } from "@/lib/catalog-api";
import { getCatalogue, saveCatalogue } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import { venueDisplayName } from "@/lib/restaurant-identity";

export default function ManageCataloguePage() {
  const params = useParams<{ id: string }>();
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [entry, setEntry] = useState<StoredCatalogue | null | undefined>();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!organizationId || !params.id) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const cached = getCatalogue(params.id, organizationId);
    if (cached) {
      setEntry(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    getCatalogueApi(params.id, organizationId)
      .then((row) => {
        if (!cancelled) {
          setEntry(row ?? getCatalogue(params.id, organizationId) ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setEntry(getCatalogue(params.id, organizationId) ?? null);
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
  }, [organizationId, params.id]);

  function handleUpdated(row: StoredCatalogue) {
    saveCatalogue(row);
    setEntry(row);
  }

  if (!organizationId) {
    return null;
  }

  return (
    <DashboardShell title="Manage Catalogue">
      <Container className="py-8">
        {loading ? (
          <CatalogueLoading />
        ) : !entry ? (
          <p className="text-sm text-muted-foreground">Catalogue not found.</p>
        ) : (
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold text-foreground">{venueDisplayName(entry.result)}</h1>
              <p className="text-sm text-muted-foreground">Owner catalogue management</p>
            </div>
            <CatalogueWorkspaceNav catalogueId={entry.id} active="manage" />
            <ManageCatalogueView entry={entry} organizationId={organizationId} onUpdated={handleUpdated} />
          </div>
        )}
      </Container>
      <BabaAiDock catalogueId={params.id} />
    </DashboardShell>
  );
}
