"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ItemQualityAspect, ItemQualityRow } from "@/lib/item-quality";
import { humanFailureReason, letterBadgeClass } from "@/lib/grade-ui";
import { catalogueMediaHref } from "@/lib/media-ui";
import { cn } from "@/lib/utils";
import type { ImprovementLine, ImprovementProposal } from "@/lib/improvement-types";
import { currentDisplay, proposedDisplay } from "@/components/improvement-preview-view";

export function ItemQualityBoard({
  rows,
  catalogueId,
  proposingCheckId = null,
  proposingPath = null,
  onImprove,
  proposals = [],
  onApply,
  onCancel,
  resolvingProposalId = null,
}: {
  rows: ItemQualityRow[];
  catalogueId?: string;
  proposingCheckId?: string | null;
  proposingPath?: string | null;
  onImprove: (checkId: string, paths?: string[], instruction?: string, refiningProposalId?: string) => void;
  proposals?: ImprovementProposal[];
  onApply?: (proposal: ImprovementProposal) => void;
  onCancel?: (proposal: ImprovementProposal) => void;
  resolvingProposalId?: string | null;
}) {
  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">No menu items are available to grade yet.</p>;
  }

  const canImproveAny = rows.some((r) => r.aspects.some((a) => a.canImprove));

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Item quality</h2>
          <p className="text-sm text-muted-foreground">
            Each listing shows Description, Tags, Image, and Price from the current grade. Improve one aspect at a time or improve all items.
          </p>
        </div>
        {canImproveAny ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!!proposingCheckId}
            onClick={() => onImprove("missing_description")}
          >
            {proposingCheckId && (proposingPath === "ALL" || !proposingPath)
              ? "Generating for all…"
              : "Improve all weak items"}
          </Button>
        ) : null}
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <article key={row.itemPath} className="space-y-3 rounded-lg border border-border bg-background p-4">
            <div className="flex items-center gap-3">
              {row.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={row.imageUrl} alt="" className="h-12 w-12 rounded object-cover" />
              ) : (
                <span className="flex h-12 w-12 items-center justify-center rounded bg-muted text-[10px] text-muted-foreground">
                  No photo
                </span>
              )}
              <div>
                <h3 className="text-sm font-medium">{row.name}</h3>
                <p className="text-xs text-muted-foreground">{row.category}</p>
              </div>
            </div>
            <ul className="space-y-2">
              {row.aspects.map((aspect) => {
                const isBusy =
                  proposingCheckId === aspect.checkId &&
                  (proposingPath === aspect.path || proposingPath === "ALL");
                const activeProposal = proposals.find(
                  (p) =>
                    (p.status === "READY" || p.status === "PARTIAL" || p.status === "FAILED") &&
                    p.lines.some((l) => l.path === aspect.path),
                );
                const activeLine = activeProposal?.lines.find((l) => l.path === aspect.path);

                return (
                  <AspectRow
                    key={aspect.key}
                    aspect={aspect}
                    catalogueId={catalogueId}
                    busy={isBusy}
                    anyBusy={!!proposingCheckId}
                    onImprove={onImprove}
                    proposal={activeProposal}
                    proposalLine={activeLine}
                    onApply={onApply}
                    onCancel={onCancel}
                    resolvingProposalId={resolvingProposalId}
                  />
                );
              })}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

function AspectRow({
  aspect,
  catalogueId,
  busy,
  anyBusy,
  onImprove,
  proposal,
  proposalLine,
  onApply,
  onCancel,
  resolvingProposalId,
}: {
  aspect: ItemQualityAspect;
  catalogueId?: string;
  busy: boolean;
  anyBusy: boolean;
  onImprove: (checkId: string, paths?: string[], instruction?: string, refiningProposalId?: string) => void;
  proposal?: ImprovementProposal;
  proposalLine?: ImprovementLine;
  onApply?: (proposal: ImprovementProposal) => void;
  onCancel?: (proposal: ImprovementProposal) => void;
  resolvingProposalId?: string | null;
}) {
  const [instruction, setInstruction] = useState("");
  const image = aspect.key === "image";
  const mode = proposalLine?.provenance?.mode;
  const isRefined = mode === "OWNER_REFINED";

  return (
    <li className="rounded-md border border-border px-3 py-2 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="w-24 text-sm font-medium">{aspect.label}</span>
        <span
          className={cn(
            "inline-flex h-7 min-w-7 items-center justify-center rounded-full px-2 text-xs font-semibold",
            letterBadgeClass(aspect.letter),
          )}
        >
          {aspect.letter}
        </span>
        <span className="min-w-0 flex-1 text-sm text-muted-foreground">{aspect.status}</span>
        {image && catalogueId ? (
          <Button type="button" size="sm" variant="outline" asChild>
            <a href={catalogueMediaHref(catalogueId, { path: aspect.path })}>Improve with AI</a>
          </Button>
        ) : null}
        {!image && aspect.canImprove && aspect.checkId ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={anyBusy}
            onClick={() => onImprove(aspect.checkId as string, [aspect.path])}
          >
            {busy ? "Generating…" : "Improve with AI"}
          </Button>
        ) : null}
      </div>

      {proposalLine && proposal ? (
        <div className="mt-2 space-y-2 rounded-md border border-primary/30 bg-muted/30 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-primary">✨ Baba’s Proposed {aspect.label}</span>
              <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                {isRefined ? "AI generated · Owner refined" : "AI generated"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {onApply && (proposal.status === "READY" || proposal.status === "PARTIAL") && proposalLine.status === "READY" ? (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => onApply(proposal)}
                  disabled={resolvingProposalId === proposal.id}
                >
                  {resolvingProposalId === proposal.id ? "Replacing…" : "Replace with this"}
                </Button>
              ) : null}
              {onCancel &&
              (proposal.status === "READY" || proposal.status === "PARTIAL" || proposal.status === "FAILED") ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onCancel(proposal)}
                  disabled={resolvingProposalId === proposal.id}
                >
                  Cancel
                </Button>
              ) : null}
            </div>
          </div>
          {proposalLine.status === "FAILED" || proposalLine.failure_reason ? (
            <div className="space-y-1 rounded border border-destructive/30 bg-destructive/10 p-2 text-destructive">
              <p className="text-xs font-semibold">Generation could not be completed</p>
              <p className="text-xs">{humanFailureReason(proposalLine.failure_reason)}</p>
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Current: </span>
                {currentDisplay(proposalLine)}
              </p>
              <p className="text-sm font-medium text-foreground">
                <span className="text-xs font-normal text-muted-foreground">Proposed: </span>
                {proposedDisplay(proposalLine)}
              </p>
            </div>
          )}

          {aspect.checkId && (proposal.status === "READY" || proposal.status === "PARTIAL") ? (
            <form
              className="mt-2 flex flex-wrap items-center gap-2 pt-1 border-t border-border/50"
              onSubmit={(e) => {
                e.preventDefault();
                if (!instruction.trim() || busy) return;
                onImprove(aspect.checkId as string, [aspect.path], instruction.trim(), proposal.id);
                setInstruction("");
              }}
            >
              <Input
                type="text"
                className="h-8 min-w-[200px] flex-1 text-xs bg-background"
                placeholder="Tell Baba what you'd like to change..."
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={busy}
              />
              <Button type="submit" size="sm" variant="outline" className="h-8 text-xs" disabled={busy || !instruction.trim()}>
                {busy ? "Refining…" : "Refine proposal"}
              </Button>
            </form>
          ) : null}

          {proposalLine.why ? (
            <p className="text-xs text-muted-foreground">Why: {proposalLine.why}</p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
