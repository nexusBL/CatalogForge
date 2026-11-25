"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CatalogueLoading, CatalogueView } from "@/components/catalogue-view";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { authClient } from "@/lib/auth-client";
import { getCatalogueApi } from "@/lib/catalog-api";
import { CATALOGUES_CHANGED_EVENT, getCatalogue } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import Link from "next/link";
import { catalogueImprovementsHref } from "@/lib/improvement-ui";

export default function CatalogueDetailPage() {
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

  useEffect(() => {
    if (!organizationId || !params.id || typeof window === "undefined") {
      return;
    }
    const onCataloguesChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ organizationId?: string }>).detail;
      if (detail?.organizationId && detail.organizationId !== organizationId) {
        return;
      }
      const local = getCatalogue(params.id, organizationId);
      if (local) {
        setEntry(local);
      }
      void getCatalogueApi(params.id, organizationId).then((row) => {
        if (row) {
          setEntry(row);
        }
      });
    };
    window.addEventListener(CATALOGUES_CHANGED_EVENT, onCataloguesChanged);
    return () => window.removeEventListener(CATALOGUES_CHANGED_EVENT, onCataloguesChanged);
  }, [organizationId, params.id]);

  return (
    <DashboardShell title="Catalogue">
      <Container className="space-y-6 py-6">
        {params.id ? <CatalogueWorkspaceNav catalogueId={params.id} active="catalogue" /> : null}
        {loading ? <CatalogueLoading /> : null}
        {!loading && entry ? (
          <>
            <p className="text-sm text-muted-foreground">
              This page is the live menu. Open{" "}
              <Link className="underline" href={`/catalogues/${params.id}/manage`}>
                Manage Catalogue
              </Link>{" "}
              to edit products directly, or{" "}
              <Link className="underline" href={catalogueImprovementsHref(params.id)}>
                Grade / AI Improvements
              </Link>{" "}
              for quality scores and AI proposals.
            </p>
            <CatalogueView catalogue={entry.result} />
            {params.id ? <BabaAiDock catalogueId={params.id} currentRoute={`/catalogues/${params.id}`} /> : null}
          </>
        ) : null}
        {!loading && !entry ? (
          <p className="text-sm text-muted-foreground">Catalogue not found for this restaurant.</p>
        ) : null}
      </Container>
    </DashboardShell>
  );
}
