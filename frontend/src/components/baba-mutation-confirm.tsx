"use client";

import { Button } from "@/components/ui/button";
import type { MutationProposalView } from "@/lib/assistant-types";

const OPERATION_LABEL: Record<string, string> = {
  change_price: "Price",
  rename_item: "Name",
  update_description: "Description",
  update_labels: "Tags",
  move_item: "Category",
  add_item: "New item",
  remove_item: "Remove item",
  improve_image: "Image",
  generate_video: "Video",
};

export function BabaMutationConfirm({
  proposal,
  disabled,
  onConfirm,
  onCancel,
}: {
  proposal: MutationProposalView;
  disabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (proposal.status !== "PENDING" || !proposal.confirm_token) {
    return null;
  }
  const field = OPERATION_LABEL[proposal.operation] || "Change";
  return (
    <div className="space-y-3 rounded-md border border-border p-3">
      <div className="space-y-1 text-sm">
        {proposal.item_name ? <p className="font-medium">{proposal.item_name}</p> : null}
        {proposal.category_name ? <p className="text-xs text-muted-foreground">{proposal.category_name}</p> : null}
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{field}</p>
        <p className="whitespace-pre-wrap text-muted-foreground">{proposal.current_value || "(none)"}</p>
        <p aria-hidden>↓</p>
        <p className="whitespace-pre-wrap">{proposal.proposed_value}</p>
        {proposal.operation === "remove_item" ? (
          <p className="text-xs text-destructive">This permanently removes the item from the catalogue.</p>
        ) : null}
        {!proposal.writes_payload ? (
          <p className="text-xs text-muted-foreground">
            This starts a media job. The live catalogue photo/video is not replaced until you apply a generated candidate in Media.
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={onConfirm} disabled={disabled}>
          Confirm change
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel} disabled={disabled}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
