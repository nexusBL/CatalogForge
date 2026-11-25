"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { AiImprovementsView } from "@/components/ai-improvements-view";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { EditHistoryPanel } from "@/components/edit-history-panel";
import { authClient } from "@/lib/auth-client";
import {
  CatalogApiError,
  applyImprovementApi,
  cancelImprovementApi,
  createImprovementApi,
  getCatalogueApi,
  getGradeExplanationApi,
  gradeCatalogueApi,
  listHistoryApi,
  listImprovementsApi,
  rollbackHistoryApi,
} from "@/lib/catalog-api";
import { getCatalogue, saveCatalogue } from "@/lib/catalogue-store";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { GradeExplanation } from "@/lib/grade-types";
import type { EditHistoryRecord } from "@/lib/history-types";
import { improvementRequestPaths, isSupportedImprovementCheck } from "@/lib/improvement-ui";
import type { ImprovementProposal } from "@/lib/improvement-types";

function CatalogueImprovementsPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const requestedCheckId = searchParams.get("check_id");
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [explanation, setExplanation] = useState<GradeExplanation | null>(null);
  const [catalogue, setCatalogue] = useState<CatalogCreateResponse | null>(null);
  const [proposals, setProposals] = useState<ImprovementProposal[]>([]);
  const [history, setHistory] = useState<EditHistoryRecord[]>([]);
  const [rollingBackId, setRollingBackId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [proposingCheckId, setProposingCheckId] = useState<string | null>(null);
  const [proposingPath, setProposingPath] = useState<string | null>(null);
  const [resolvingProposalId, setResolvingProposalId] = useState<string | null>(null);
  const [appliedGrade, setAppliedGrade] = useState<string | null>(null);
  const autoPreviewed = useRef<string | null>(null);

  const onPreview = useCallback(
    (checkId: string, paths?: string[], instruction?: string, refiningProposalId?: string) => {
      if (!organizationId || !params.id || proposingCheckId) {
        return;
      }
      setProposingCheckId(checkId);
      setProposingPath(paths?.length ? paths[0] : "ALL");
      setError(null);
      createImprovementApi(params.id, organizationId, {
        check_id: checkId,
        ...(paths?.length ? { paths } : {}),
        ...(instruction ? { instruction } : {}),
        ...(refiningProposalId ? { refining_proposal_id: refiningProposalId } : {}),
      })
        .then((proposal) => {
          setProposals((current) => [proposal, ...current.filter((row) => row.id !== proposal.id)]);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof CatalogApiError ? caught.message : "Could not generate an improvement preview.");
        })
        .finally(() => {
          setProposingCheckId(null);
          setProposingPath(null);
        });
    },
    [organizationId, params.id, proposingCheckId],
  );

  const onApply = useCallback(
    (proposal: ImprovementProposal) => {
      if (!organizationId || !params.id) {
        return;
      }
      setResolvingProposalId(proposal.id);
      setError(null);
      applyImprovementApi(params.id, organizationId, proposal.id)
        .then((row) => {
          setProposals((current) => [row.proposal, ...current.filter((item) => item.id !== row.proposal.id)]);
          if (row.grade_letter) {
            setAppliedGrade(
              row.grade_score != null ? `${row.grade_letter} (${row.grade_score})` : row.grade_letter,
            );
          }
          return Promise.all([
            getCatalogueApi(params.id, organizationId),
            getGradeExplanationApi(params.id, organizationId),
            listHistoryApi(params.id, organizationId),
          ]).then(([catalogueRow, explanationRow, historyRow]) => {
            if (catalogueRow) {
              saveCatalogue(catalogueRow);
              setCatalogue(catalogueRow.result);
            }
            if (explanationRow) {
              setExplanation(explanationRow);
            }
            setHistory(historyRow.records);
          });
        })
        .catch((caught: unknown) => {
          setError(caught instanceof CatalogApiError ? caught.message : "Could not apply this improvement.");
        })
        .finally(() => {
          setResolvingProposalId(null);
        });
    },
    [organizationId, params.id],
  );

  const onCancelProposal = useCallback(
    (proposal: ImprovementProposal) => {
      if (!organizationId || !params.id) {
        return;
      }
      setResolvingProposalId(proposal.id);
      setError(null);
      cancelImprovementApi(params.id, organizationId, proposal.id)
        .then((row) => {
          setProposals((current) => [row, ...current.filter((item) => item.id !== row.id)]);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof CatalogApiError ? caught.message : "Could not cancel this improvement.");
        })
        .finally(() => {
          setResolvingProposalId(null);
        });
    },
    [organizationId, params.id],
  );

  const onRollback = useCallback(
    (record: EditHistoryRecord) => {
      if (!organizationId || !params.id) {
        return;
      }
      setRollingBackId(record.id);
      setError(null);
      rollbackHistoryApi(params.id, organizationId, record.id)
        .then(() =>
          Promise.all([
            getCatalogueApi(params.id, organizationId),
            getGradeExplanationApi(params.id, organizationId),
            listHistoryApi(params.id, organizationId),
          ]),
        )
        .then(([catalogueRow, explanationRow, historyRow]) => {
          if (catalogueRow) {
            saveCatalogue(catalogueRow);
            setCatalogue(catalogueRow.result);
          }
          if (explanationRow) {
            setExplanation(explanationRow);
          }
          setHistory(historyRow.records);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof CatalogApiError ? caught.message : "Could not roll back this catalogue change.");
        })
        .finally(() => {
          setRollingBackId(null);
        });
    },
    [organizationId, params.id],
  );

  useEffect(() => {
    if (!organizationId || !params.id) {
      return;
    }
    let cancelled = false;
    getCatalogueApi(params.id, organizationId)
      .then((row) => {
        if (!cancelled) {
          setCatalogue((row ?? getCatalogue(params.id, organizationId))?.result ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogue(getCatalogue(params.id, organizationId)?.result ?? null);
        }
      });
    getGradeExplanationApi(params.id, organizationId)
      .then((row) => {
        if (cancelled) return;
        if (row) {
          setExplanation(row);
        } else {
          return gradeCatalogueApi(params.id, organizationId).then((gradedRow: GradeExplanation) => {
            if (!cancelled) {
              setExplanation(gradedRow);
            }
          });
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setExplanation(null);
          setError(caught instanceof CatalogApiError ? caught.message : "Could not load this catalogue grade.");
        }
      });
    listImprovementsApi(params.id, organizationId)
      .then((rows) => {
        if (!cancelled) {
          setProposals(rows);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof CatalogApiError ? caught.message : "Could not load improvement previews.");
        }
      });
    listHistoryApi(params.id, organizationId)
      .then((row) => {
        if (!cancelled) {
          setHistory(row.records);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHistory([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, params.id]);

  useEffect(() => {
    if (!requestedCheckId || !organizationId || !params.id || !explanation) {
      return;
    }
    if (!isSupportedImprovementCheck(requestedCheckId)) {
      return;
    }
    const key = `${params.id}:${requestedCheckId}`;
    if (autoPreviewed.current === key) {
      return;
    }
    autoPreviewed.current = key;
    const finding = explanation.findings.find((row) => row.check_id === requestedCheckId);
    onPreview(requestedCheckId, finding ? improvementRequestPaths(finding) : undefined);
  }, [requestedCheckId, organizationId, params.id, explanation, onPreview]);

  return (
    <DashboardShell title="AI Improvements">
      <Container className="space-y-6 py-6">
        {params.id ? <CatalogueWorkspaceNav catalogueId={params.id} active="improvements" /> : null}
        {appliedGrade ? (
          <p className="text-sm">Live catalogue updated. Recalculated grade: {appliedGrade}</p>
        ) : null}
        <AiImprovementsView
          explanation={explanation}
          proposals={proposals}
          error={error}
          onPreview={onPreview}
          proposingCheckId={proposingCheckId}
          proposingPath={proposingPath}
          onApply={onApply}
          onCancel={onCancelProposal}
          resolvingProposalId={resolvingProposalId}
          catalogue={catalogue}
          catalogueId={params.id}
        />
        <EditHistoryPanel records={history} rollingBackId={rollingBackId} onRollback={onRollback} />
        {params.id ? <BabaAiDock catalogueId={params.id} currentRoute={`/catalogues/${params.id}/improvements`} /> : null}
      </Container>
    </DashboardShell>
  );
}

export default function CatalogueImprovementsRoute() {
  return (
    <Suspense
      fallback={
        <DashboardShell title="AI Improvements">
          <Container className="py-6">
            <p className="text-sm text-muted-foreground">Loading AI Improvements…</p>
          </Container>
        </DashboardShell>
      }
    >
      <CatalogueImprovementsPage />
    </Suspense>
  );
}
