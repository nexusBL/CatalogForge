"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { ImprovementPreviewView } from "@/components/improvement-preview-view";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { GradeExplanation, GradeFinding } from "@/lib/grade-types";
import { checkTitle, letterBadgeClass, resolveFindingProducts } from "@/lib/grade-ui";
import { cn } from "@/lib/utils";
import {
  IMPROVEMENT_KIND_LABEL,
  improvementRequestPaths,
  kindForCheckId,
  supportedImprovementFindings,
} from "@/lib/improvement-ui";
import { ItemQualityBoard } from "@/components/item-quality-board";
import { itemQualityRows } from "@/lib/item-quality";
import type { ImprovementProposal } from "@/lib/improvement-types";

const LABELS_DRIVER = {
  check_id: "empty_item_labels",
  why: "Add catalogue labels for items that currently have none.",
  action: "Propose labels for items that have none.",
  affected_count: null as number | null,
};

export function AiImprovementsView({
  explanation,
  proposals,
  error = null,
  onPreview,
  proposingCheckId = null,
  proposingPath = null,
  onApply,
  onCancel,
  resolvingProposalId = null,
  catalogue = null,
  catalogueId,
}: {
  explanation: GradeExplanation | null;
  proposals: ImprovementProposal[];
  error?: string | null;
  onPreview: (checkId: string, paths?: string[], instruction?: string, refiningProposalId?: string) => void;
  proposingCheckId?: string | null;
  proposingPath?: string | null;
  onApply?: (proposal: ImprovementProposal) => void;
  onCancel?: (proposal: ImprovementProposal) => void;
  resolvingProposalId?: string | null;
  catalogue?: CatalogCreateResponse | null;
  catalogueId?: string;
}) {
  const findings = supportedImprovementFindings(explanation);
  const itemRows = useMemo(() => itemQualityRows(catalogue, explanation), [catalogue, explanation]);
  const opportunities = useMemo(() => {
    const rows: Array<{
      check_id: string;
      why: string;
      action: string;
      affected_count: number | null;
      finding?: GradeFinding;
    }> = findings.map((finding) => ({
      check_id: finding.check_id,
      why: finding.why,
      action: finding.recommendation?.action || finding.why,
      affected_count: finding.evidence.affected_count,
      finding,
    }));
    if (explanation) {
      rows.push({
        check_id: LABELS_DRIVER.check_id,
        why: LABELS_DRIVER.why,
        action: LABELS_DRIVER.action,
        affected_count: LABELS_DRIVER.affected_count,
      });
    }
    return rows;
  }, [explanation, findings]);

  return (
    <section className="space-y-6 rounded-xl border border-border bg-card p-5 text-card-foreground">
      <div>
        <h1 className="text-lg font-medium">Grade / AI Improvements</h1>
        <p className="text-sm text-muted-foreground">
          See what is weak on each listing, generate a before/after proposal, then replace the live catalogue value.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Grade measures catalogue quality. AI Improvements is Baba’s proposed-change workflow.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <p className="font-semibold">AI Improvement Error</p>
          <p>{error}</p>
        </div>
      ) : null}

      {explanation ? (
        <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border p-4">
          <span
            className={cn(
              "flex h-14 w-14 items-center justify-center rounded-xl text-2xl font-semibold",
              letterBadgeClass(explanation.overall_grade),
            )}
          >
            {explanation.overall_grade}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Overall catalogue grade</p>
            <p className="text-xs text-muted-foreground">{Math.round(explanation.overall_score)} / 100</p>
          </div>
          <ul className="flex flex-wrap gap-2">
            {explanation.section_grades.map((section) => (
              <li key={section.section} className="rounded-md border border-border px-3 py-2 text-sm">
                <span className="text-xs text-muted-foreground">{section.label}</span>
                <span className="ml-2 font-medium">{section.letter}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <ItemQualityBoard
        rows={itemRows}
        catalogueId={catalogueId || explanation?.catalogue_id}
        proposingCheckId={proposingCheckId}
        proposingPath={proposingPath}
        onImprove={onPreview}
        proposals={proposals}
        onApply={onApply}
        onCancel={onCancel}
        resolvingProposalId={resolvingProposalId}
      />

      {!explanation ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">No AI improvements available</p>
          <p className="text-sm text-muted-foreground">
            Your catalogue currently has no supported improvement findings.
          </p>
        </div>
      ) : opportunities.length === 0 ? (
        <div className="space-y-1">
          <p className="text-sm font-medium">No AI improvements available</p>
          <p className="text-sm text-muted-foreground">
            Your catalogue currently has no supported improvement findings.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <h2 className="text-sm font-medium">What Baba can improve</h2>
          {opportunities.map((row) => {
            const kind = kindForCheckId(row.check_id);
            const products = row.finding ? resolveFindingProducts(row.finding, catalogue).slice(0, 6) : [];
            return (
              <article key={row.check_id} className="space-y-2 rounded-lg border border-border bg-background p-4">
                <h3 className="text-sm font-medium">{checkTitle(row.check_id)}</h3>
                <p className="text-sm">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Problem: </span>
                  {row.why}
                </p>
                <p className="text-sm">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Recommended action:{" "}
                  </span>
                  {row.action}
                </p>
                {row.affected_count != null ? (
                  <p className="text-sm text-muted-foreground">
                    {row.affected_count} {row.affected_count === 1 ? "item" : "items"} affected
                  </p>
                ) : null}
                {kind ? (
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    Improvement type: {IMPROVEMENT_KIND_LABEL[kind]}
                  </p>
                ) : null}
                {products.length ? (
                  <ul className="flex flex-wrap gap-2">
                    {products.map((product) => (
                      <li key={product.path} className="flex items-center gap-2 rounded-md border border-border px-2 py-1">
                        {product.imageUrl ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={product.imageUrl} alt="" className="h-8 w-8 rounded object-cover" />
                        ) : (
                          <span className="h-8 w-8 rounded bg-muted" />
                        )}
                        <span className="text-xs">{product.name}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onPreview(row.check_id, row.finding ? improvementRequestPaths(row.finding) : undefined)}
                  disabled={proposingCheckId === row.check_id}
                >
                  {proposingCheckId === row.check_id ? "Improving…" : "Improve"}
                </Button>
              </article>
            );
          })}
        </div>
      )}

      <ImprovementPreviewView
        catalogueId={explanation?.catalogue_id}
        catalogue={catalogue}
        proposals={proposals}
        error={error}
        onRetry={(checkId) => {
          const finding = findings.find((row) => row.check_id === checkId);
          onPreview(checkId, finding ? improvementRequestPaths(finding) : undefined);
        }}
        retryingCheckId={proposingCheckId}
        onApply={onApply}
        onCancel={onCancel}
        resolvingProposalId={resolvingProposalId}
      />
    </section>
  );
}
