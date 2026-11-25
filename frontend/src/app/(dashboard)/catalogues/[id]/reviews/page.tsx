"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { ReviewIntelligenceView } from "@/components/review-intelligence-view";
import { authClient } from "@/lib/auth-client";
import {
  CatalogApiError,
  collectReviewsApi,
  createReviewIntelligenceApi,
  getReviewIntelligenceApi,
  listReviewsApi,
} from "@/lib/catalog-api";
import type { ReviewIntelligence, ReviewListResponse } from "@/lib/review-types";

export default function CatalogueReviewsPage() {
  const params = useParams<{ id: string }>();
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [reviews, setReviews] = useState<ReviewListResponse | null>(null);
  const [intelligence, setIntelligence] = useState<ReviewIntelligence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [rating, setRating] = useState("");
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [collecting, setCollecting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const reload = useCallback(() => {
    if (!organizationId || !params.id) {
      return;
    }
    setLoading(true);
    listReviewsApi(params.id, organizationId, offset)
      .then((row) => setReviews(row))
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not load reviews.");
      })
      .finally(() => setLoading(false));
    getReviewIntelligenceApi(params.id, organizationId)
      .then((row) => setIntelligence(row))
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not load review intelligence.");
      });
  }, [organizationId, params.id, offset]);

  useEffect(() => {
    reload();
  }, [reload]);

  const onCollect = useCallback(() => {
    if (!organizationId || !params.id || !body.trim()) {
      return;
    }
    const parsed = rating.trim() ? Number(rating) : undefined;
    if (parsed != null && Number.isNaN(parsed)) {
      setError("Observed rating must be a number.");
      return;
    }
    setCollecting(true);
    setError(null);
    collectReviewsApi(params.id, organizationId, [
      { body: body.trim(), ...(parsed != null ? { observed_rating: parsed } : {}) },
    ])
      .then(() => {
        setBody("");
        setRating("");
        reload();
      })
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not collect reviews.");
      })
      .finally(() => setCollecting(false));
  }, [organizationId, params.id, body, rating, reload]);

  const onAnalyze = useCallback(() => {
    if (!organizationId || !params.id) {
      return;
    }
    setAnalyzing(true);
    setError(null);
    createReviewIntelligenceApi(params.id, organizationId)
      .then((row) => {
        setIntelligence(row);
        reload();
      })
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not analyze reviews.");
      })
      .finally(() => setAnalyzing(false));
  }, [organizationId, params.id, reload]);

  return (
    <DashboardShell title="Customer reviews">
      <Container className="space-y-6 py-6">
        {params.id ? <CatalogueWorkspaceNav catalogueId={params.id} active="reviews" /> : null}
        <ReviewIntelligenceView
          reviews={reviews}
          intelligence={intelligence}
          error={error}
          loading={loading}
          body={body}
          rating={rating}
          collecting={collecting}
          analyzing={analyzing}
          onBodyChange={setBody}
          onRatingChange={setRating}
          onCollect={onCollect}
          onAnalyze={onAnalyze}
            organizationId={organizationId}
            onPrevPage={() => setOffset((current) => Math.max(0, current - 50))}
          onNextPage={() => setOffset((current) => current + 50)}
        />
        {params.id ? <BabaAiDock catalogueId={params.id} currentRoute={`/catalogues/${params.id}/reviews`} /> : null}
      </Container>
    </DashboardShell>
  );
}
