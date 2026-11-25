"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import { MediaStudioView } from "@/components/media-studio-view";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { authClient } from "@/lib/auth-client";
import {
  CatalogApiError,
  applyMediaJobApi,
  assistMediaPromptApi,
  createMediaJobApi,
  getCatalogueApi,
  getMediaStudioApi,
  revertMediaApi,
} from "@/lib/catalog-api";
import { saveCatalogue } from "@/lib/catalogue-store";
import type { MediaOperation, MediaStudioResponse } from "@/lib/media-types";
import { publicMediaError, type MediaStudioTab } from "@/lib/media-ui";

function CatalogueMediaPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [studio, setStudio] = useState<MediaStudioResponse | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(searchParams.get("path"));
  const [tab, setTab] = useState<MediaStudioTab>("images");
  const [operation, setOperation] = useState<MediaOperation>("enhance");
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const queryPath = searchParams.get("path");

  useEffect(() => {
    if (queryPath) {
      setSelectedPath(queryPath);
    }
  }, [queryPath]);

  const reload = useCallback(() => {
    if (!organizationId || !params.id) {
      return;
    }
    const pathParam = selectedPath || queryPath || undefined;
    getMediaStudioApi(
      params.id,
      organizationId,
      searchParams.get("proposal_id") || undefined,
      pathParam,
    )
      .then((row) => {
        setStudio(row);
        setSelectedPath((current) => current || queryPath || row.handoff_path || row.items[0]?.path || null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not load Generated Media.");
      });
  }, [organizationId, params.id, queryPath, searchParams, selectedPath]);

  useEffect(() => {
    reload();
  }, [reload]);

  const onGenerate = (nextOperation?: MediaOperation) => {
    if (!organizationId || !params.id || !selectedPath) {
      return;
    }
    if (nextOperation) {
      setOperation(nextOperation);
    }
    setGenerating(true);
    setError(null);
    const item = studio?.items.find((row) => row.path === selectedPath);
    const chosen = nextOperation ?? operation;
    const op: MediaOperation =
      tab === "gifs" ? "image_to_video" : !item?.has_usable_image && chosen !== "edit" ? "generate_image" : chosen;
    const pathJobs = (studio?.jobs ?? []).filter((row) => row.path === selectedPath);
    const parent = pathJobs.find((row) => row.status === "READY");
    createMediaJobApi(params.id, organizationId, {
      path: selectedPath,
      operation: op,
      prompt: prompt || undefined,
      proposal_id: searchParams.get("proposal_id") || undefined,
      parent_candidate_id: parent?.active_candidate_id || parent?.candidates[0]?.id,
      revision_ordinal: pathJobs.length,
    })
      .then((job) => {
        if (job.status === "FAILED") {
          setError(publicMediaError(job.error, tab) || "Could not generate media.");
        }
        reload();
      })
      .catch((caught: unknown) => {
        const raw = caught instanceof CatalogApiError ? caught.message : "Could not generate media.";
        setError(publicMediaError(raw, tab) || raw);
      })
      .finally(() => setGenerating(false));
  };

  const onAssist = () => {
    if (!organizationId || !params.id || !selectedPath) {
      return;
    }
    assistMediaPromptApi(params.id, organizationId, {
      path: selectedPath,
      kind: tab === "gifs" ? "image_to_video" : "edit",
      prompt: prompt || undefined,
    })
      .then((row) => setPrompt(row.suggested_prompt))
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not assist the prompt.");
      });
  };

  const onApplyLive = () => {
    if (!organizationId || !params.id || !selectedPath || !studio) {
      return;
    }
    const pathJobs = (studio.jobs || []).filter((row) => row.path === selectedPath);
    const job = pathJobs.find((row) => row.status === "READY" && (row.active_candidate_id || row.candidates[0]));
    if (!job) {
      setError("Generate a ready candidate before applying it to the catalogue.");
      return;
    }
    setApplying(true);
    setError(null);
    applyMediaJobApi(params.id, organizationId, job.id)
      .then(() => getCatalogueApi(params.id, organizationId))
      .then((row) => {
        if (row) {
          saveCatalogue(row);
        }
        reload();
      })
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not apply generated media.");
      })
      .finally(() => setApplying(false));
  };

  const onRevert = () => {
    if (!organizationId || !params.id || !selectedPath) {
      return;
    }
    revertMediaApi(params.id, organizationId, selectedPath, "original")
      .then(() => reload())
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not revert.");
      });
  };

  return (
    <DashboardShell title="Generated Media">
      <Container className="space-y-6 py-6">
        {params.id ? <CatalogueWorkspaceNav catalogueId={params.id} active="media" /> : null}
        <p className="text-sm text-muted-foreground">
          Generate a candidate, compare before and after, then apply it to replace the live catalogue photo or GIF.
        </p>
        {organizationId ? (
          <MediaStudioView
            catalogueId={params.id}
            organizationId={organizationId}
            studio={studio}
            selectedPath={selectedPath}
            tab={tab}
            operation={operation}
            prompt={prompt}
            generating={generating}
            error={error}
            onSelectPath={setSelectedPath}
            onTab={setTab}
            onOperation={setOperation}
            onPrompt={setPrompt}
            onGenerate={onGenerate}
            onAssist={onAssist}
            onRevert={onRevert}
            onApplyLive={onApplyLive}
            applying={applying}
          />
        ) : (
          <p className="text-sm text-muted-foreground">Select an organization to open Generated Media.</p>
        )}
        {params.id ? <BabaAiDock catalogueId={params.id} currentRoute={`/catalogues/${params.id}/media`} /> : null}
      </Container>
    </DashboardShell>
  );
}

export default function CatalogueMediaRoute() {
  return (
    <Suspense
      fallback={
        <DashboardShell title="Generated Media">
          <Container className="py-6">
            <p className="text-sm text-muted-foreground">Loading Generated Media…</p>
          </Container>
        </DashboardShell>
      }
    >
      <CatalogueMediaPage />
    </Suspense>
  );
}
