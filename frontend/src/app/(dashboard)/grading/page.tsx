"use client";

import { useEffect, useMemo, useState } from "react";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { GradingListView } from "@/components/grading-list-view";
import { authClient } from "@/lib/auth-client";
import { CatalogApiError, getGradeExplanationApi, listCataloguesApi } from "@/lib/catalog-api";
import { listCatalogues } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import {
  filterGradingRows,
  gradingRowFromCatalogue,
  type GradeListFilter,
  type GradingListRow,
  type VenueDomainFilter,
} from "@/lib/grading-ui";

export default function GradingListPage() {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [rows, setRows] = useState<GradingListRow[]>([]);
  const [domain, setDomain] = useState<VenueDomainFilter>("all");
  const [grade, setGrade] = useState<GradeListFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listCataloguesApi(organizationId)
      .then(async (catalogues: StoredCatalogue[]) => {
        const graded = await Promise.all(
          catalogues.map(async (row) => {
            try {
              const explanation = await getGradeExplanationApi(row.id, organizationId);
              return gradingRowFromCatalogue(
                row.id,
                row.result,
                explanation?.overall_grade ?? null,
                explanation ? explanation.overall_score : null,
              );
            } catch {
              return gradingRowFromCatalogue(row.id, row.result, null, null);
            }
          }),
        );
        if (!cancelled) {
          setRows(graded);
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        const fallback = listCatalogues(organizationId).map((row) =>
          gradingRowFromCatalogue(row.id, row.result, null, null),
        );
        setRows(fallback);
        setError(caught instanceof CatalogApiError ? caught.message : "Could not load catalogue grades.");
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

  const visible = useMemo(() => filterGradingRows(rows, domain, grade), [rows, domain, grade]);

  return (
    <DashboardShell title="Grading">
      <Container className="space-y-6 py-6">
        <div>
          <h1 className="text-xl font-medium">Grading</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            See every restaurant and dineout at a glance, then open one to fix photos, video, and catalogue quality.
          </p>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {!organizationId ? (
          <p className="text-sm text-muted-foreground">Select an organization to see catalogue grades.</p>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading grades…</p>
        ) : (
          <GradingListView rows={visible} domain={domain} grade={grade} onDomain={setDomain} onGrade={setGrade} />
        )}
      </Container>
    </DashboardShell>
  );
}
