"use client";

import { Button } from "@/components/ui/button";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import { humanFailureReason, resolvePathProduct } from "@/lib/grade-ui";
import { IMPROVEMENT_KIND_LABEL } from "@/lib/improvement-ui";
import { catalogueMediaHref } from "@/lib/media-ui";
import type { ImprovementLine, ImprovementProposal } from "@/lib/improvement-types";

export function currentDisplay(line: ImprovementLine): string {
  if (line.kind === "labels") {
    return line.current_value || "No labels";
  }
  if (line.kind === "media_handoff") {
    return line.current_value || "Current photo needs improvement";
  }
  return line.current_value || "No description";
}

export function proposedDisplay(line: ImprovementLine): string {
  if (line.kind === "labels") {
    return (
      (line.proposed_labels && line.proposed_labels.length ? line.proposed_labels.join(", ") : line.proposed_value) ||
      "No suggestion"
    );
  }
  if (line.kind === "media_handoff") {
    return line.proposed_value || "Open Generated Media to preview an image improvement";
  }
  return line.proposed_value || "No suggestion";
}

function kindLabel(line: ImprovementLine): string {
  return IMPROVEMENT_KIND_LABEL[line.kind];
}

export function ImprovementPreviewView({
  proposals,
  error = null,
  onRetry,
  retryingCheckId = null,
  onApply,
  onCancel,
  resolvingProposalId = null,
  catalogueId,
  catalogue = null,
}: {
  proposals: ImprovementProposal[];
  error?: string | null;
  onRetry?: (checkId: string) => void;
  retryingCheckId?: string | null;
  onApply?: (proposal: ImprovementProposal) => void;
  onCancel?: (proposal: ImprovementProposal) => void;
  resolvingProposalId?: string | null;
  catalogueId?: string;
  catalogue?: CatalogCreateResponse | null;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-medium">Proposed changes</h2>
        <p className="text-sm text-muted-foreground">
          Review Baba’s suggestion, then replace the live catalogue value. Replacement re-grades this catalogue.
        </p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {proposals.length === 0 ? (
        <p className="text-sm text-muted-foreground">No generated previews yet. Choose an opportunity above.</p>
      ) : (
        <div className="space-y-4">
          {proposals.map((proposal) => (
            <article key={proposal.id} className="space-y-3 rounded-lg border border-border bg-background p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    Preview status: {proposal.status}
                  </p>
                  {proposal.status === "STALE" ? (
                    <p className="mt-1 text-sm text-destructive">Catalogue changed — this preview is stale.</p>
                  ) : null}
                </div>
                {onRetry && (proposal.status === "STALE" || proposal.status === "FAILED") ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onRetry(proposal.check_id)}
                    disabled={retryingCheckId === proposal.check_id}
                  >
                    {retryingCheckId === proposal.check_id
                      ? "Generating preview…"
                      : proposal.status === "STALE"
                        ? "Generate a fresh preview"
                        : "Retry preview"}
                  </Button>
                ) : null}
                {onApply && (proposal.status === "READY" || proposal.status === "PARTIAL") ? (
                  <Button
                    type="button"
                    onClick={() => onApply(proposal)}
                    disabled={resolvingProposalId === proposal.id}
                  >
                    {resolvingProposalId === proposal.id ? "Replacing…" : "Replace with this"}
                  </Button>
                ) : null}
                {onCancel && (proposal.status === "READY" || proposal.status === "PARTIAL" || proposal.status === "FAILED") ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onCancel(proposal)}
                    disabled={resolvingProposalId === proposal.id}
                  >
                    Cancel
                  </Button>
                ) : null}
              </div>
              {proposal.lines.map((line) => {
                const product = resolvePathProduct(catalogue, line.path);
                const failed = line.status === "FAILED" && !line.proposed_value && !line.proposed_labels?.length;
                return (
                  <div key={`${proposal.id}:${line.path}`} className="space-y-2 border-t border-border pt-3">
                    <div className="flex items-center gap-3">
                      {product?.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={product.imageUrl} alt="" className="h-14 w-14 rounded object-cover" />
                      ) : (
                        <span className="flex h-14 w-14 items-center justify-center rounded bg-muted text-[10px] text-muted-foreground">
                          No photo
                        </span>
                      )}
                      <div>
                        <p className="text-sm font-medium">{product?.name || "Catalogue item"}</p>
                        <p className="text-xs text-muted-foreground">{product?.category || kindLabel(line)}</p>
                      </div>
                    </div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Improvement type: {kindLabel(line)}
                    </p>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Current</p>
                      <p className="text-sm">{currentDisplay(line)}</p>
                    </div>
                    <p className="text-xs text-muted-foreground" aria-hidden="true">
                      ↓
                    </p>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Baba’s suggestion</p>
                      {failed ? (
                        <p className="text-sm">{humanFailureReason(line.failure_reason)}</p>
                      ) : (
                        <p className="text-sm">{proposedDisplay(line)}</p>
                      )}
                      {line.kind === "media_handoff" && catalogueId ? (
                        <a
                          className="mt-2 inline-block text-sm underline"
                          href={catalogueMediaHref(catalogueId, { path: line.path, proposalId: proposal.id })}
                        >
                          Improve image
                        </a>
                      ) : null}
                    </div>
                    <details className="text-xs text-muted-foreground">
                      <summary className="cursor-pointer">Why?</summary>
                      <p className="mt-2">{line.why}</p>
                      {line.failure_reason ? <p className="mt-1">Technical details: {line.failure_reason}</p> : null}
                    </details>
                  </div>
                );
              })}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
