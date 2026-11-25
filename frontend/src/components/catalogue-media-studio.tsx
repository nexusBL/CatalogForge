"use client";

import { useCallback, useEffect, useState } from "react";
import { MediaStudioView } from "@/components/media-studio-view";
import {
  CatalogApiError,
  applyMediaJobApi,
  assistMediaPromptApi,
  createMediaJobApi,
  getMediaStudioApi,
  revertMediaApi,
} from "@/lib/catalog-api";
import type { MediaOperation, MediaStudioResponse } from "@/lib/media-types";
import { publicMediaError, type MediaStudioTab } from "@/lib/media-ui";

export function CatalogueMediaStudio({
  catalogueId,
  organizationId,
  tab,
  onTab,
}: {
  catalogueId: string;
  organizationId: string;
  tab: MediaStudioTab;
  onTab: (tab: MediaStudioTab) => void;
}) {
  const [studio, setStudio] = useState<MediaStudioResponse | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [operation, setOperation] = useState<MediaOperation>("enhance");
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    getMediaStudioApi(catalogueId, organizationId, undefined, selectedPath || undefined)
      .then((row) => {
        setStudio(row);
        setSelectedPath((current) => current || row.handoff_path || row.items[0]?.path || null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not load Generated Media.");
      });
  }, [catalogueId, organizationId, selectedPath]);

  useEffect(() => {
    reload();
  }, [reload]);

  const onGenerate = (nextOperation?: MediaOperation) => {
    if (!selectedPath) {
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
    createMediaJobApi(catalogueId, organizationId, {
      path: selectedPath,
      operation: op,
      prompt: prompt || undefined,
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
    if (!selectedPath) {
      return;
    }
    assistMediaPromptApi(catalogueId, organizationId, {
      path: selectedPath,
      kind: tab === "gifs" ? "image_to_video" : "edit",
      prompt: prompt || undefined,
    })
      .then((row) => setPrompt(row.suggested_prompt))
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not assist the prompt.");
      });
  };

  const onRevert = () => {
    if (!selectedPath) {
      return;
    }
    revertMediaApi(catalogueId, organizationId, selectedPath, "original")
      .then(() => reload())
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not revert.");
      });
  };

  const onApplyLive = () => {
    if (!selectedPath || !studio) {
      return;
    }
    const pathJobs = studio.jobs.filter((j) => j.path === selectedPath);
    const activeJob = pathJobs.find((j) => j.status === "READY" && j.active_candidate_id);
    if (!activeJob) {
      return;
    }
    setApplying(true);
    setError(null);
    applyMediaJobApi(catalogueId, organizationId, activeJob.id)
      .then(() => reload())
      .catch((caught: unknown) => {
        setError(caught instanceof CatalogApiError ? caught.message : "Could not apply media to live catalogue.");
      })
      .finally(() => setApplying(false));
  };

  return (
    <MediaStudioView
      catalogueId={catalogueId}
      organizationId={organizationId}
      studio={studio}
      selectedPath={selectedPath}
      tab={tab}
      operation={operation}
      prompt={prompt}
      generating={generating}
      error={error}
      onSelectPath={setSelectedPath}
      onTab={onTab}
      onOperation={setOperation}
      onPrompt={setPrompt}
      onGenerate={onGenerate}
      onAssist={onAssist}
      onRevert={onRevert}
      onApplyLive={onApplyLive}
      applying={applying}
    />
  );
}
