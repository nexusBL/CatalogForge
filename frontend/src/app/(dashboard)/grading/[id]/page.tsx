"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { CatalogueMediaStudio } from "@/components/catalogue-media-studio";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { GradeExplanationView } from "@/components/grade-explanation-view";
import { GradingWorkspaceNav } from "@/components/grading-workspace-nav";
import { authClient } from "@/lib/auth-client";
import { CatalogApiError, getCatalogueApi, getGradeExplanationApi, gradeCatalogueApi } from "@/lib/catalog-api";
import { getCatalogue } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import type { GradeExplanation } from "@/lib/grade-types";
import { letterBadgeClass } from "@/lib/grade-ui";
import { gradingListHref, parseGradingTab } from "@/lib/grading-ui";
import { venueDisplayName } from "@/lib/restaurant-identity";
import type { MediaStudioTab } from "@/lib/media-ui";
import { cn } from "@/lib/utils";

function GradingWorkspacePage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const tab = parseGradingTab(searchParams.get("tab"));
  const [entry, setEntry] = useState<StoredCatalogue | null | undefined>();
  const [explanation, setExplanation] = useState<GradeExplanation | null>(null);
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [gradeError, setGradeError] = useState<string | null>(null);
  const [mediaTab, setMediaTab] = useState<MediaStudioTab>(tab === "video" ? "gifs" : "images");

  useEffect(() => {
    setMediaTab(tab === "video" ? "gifs" : "images");
  }, [tab]);

  useEffect(() => {
    if (!organizationId || !params.id) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
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
    getGradeExplanationApi(params.id, organizationId)
      .then((row) => {
        if (!cancelled) {
          setExplanation(row);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setExplanation(null);
          setGradeError(error instanceof CatalogApiError ? error.message : "Could not load this catalogue grade.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, params.id]);

  const onGrade = useCallback(() => {
    if (!organizationId || !params.id) {
      return;
    }
    setGrading(true);
    setGradeError(null);
    gradeCatalogueApi(params.id, organizationId)
      .then((row) => setExplanation(row))
      .catch((error: unknown) => {
        setGradeError(error instanceof CatalogApiError ? error.message : "Could not grade this catalogue.");
      })
      .finally(() => setGrading(false));
  }, [organizationId, params.id]);

  const name = entry ? venueDisplayName(entry.result) : "Catalogue";

  return (
    <DashboardShell title="Grading">
      <Container className="space-y-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link href={gradingListHref()} className="text-sm text-muted-foreground hover:underline">
              All venues
            </Link>
            <h1 className="mt-2 text-xl font-medium">{name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Quality, photos, and video in one place so owners can see the grade and improve the listing.
            </p>
          </div>
          {explanation ? (
            <span
              className={cn(
                "inline-flex h-12 w-12 items-center justify-center rounded-full text-lg font-semibold",
                letterBadgeClass(explanation.overall_grade),
              )}
            >
              {explanation.overall_grade}
            </span>
          ) : null}
        </div>
        {params.id ? <GradingWorkspaceNav catalogueId={params.id} active={tab} /> : null}
        {loading ? <p className="text-sm text-muted-foreground">Loading quality workspace…</p> : null}
        {!loading && !entry ? (
          <p className="text-sm text-muted-foreground">Catalogue not found for this restaurant.</p>
        ) : null}
        {!loading && entry && tab === "quality" ? (
          <GradeExplanationView
            explanation={explanation}
            onGrade={onGrade}
            grading={grading}
            error={gradeError}
            catalogueId={params.id}
            catalogue={entry.result}
          />
        ) : null}
        {!loading && entry && (tab === "photos" || tab === "video") ? (
          organizationId ? (
            <CatalogueMediaStudio
              catalogueId={params.id}
              organizationId={organizationId}
              tab={mediaTab}
              onTab={setMediaTab}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Select an organization to open photos and video.</p>
          )
        ) : null}
        {params.id ? <BabaAiDock catalogueId={params.id} currentRoute={`/grading/${params.id}`} /> : null}
      </Container>
    </DashboardShell>
  );
}

export default function GradingWorkspaceRoute() {
  return (
    <Suspense
      fallback={
        <DashboardShell title="Grading">
          <Container className="py-6">
            <p className="text-sm text-muted-foreground">Loading quality workspace…</p>
          </Container>
        </DashboardShell>
      }
    >
      <GradingWorkspacePage />
    </Suspense>
  );
}
