"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { canDeleteDiscoveryJob, DISCOVERY_JOB_DELETE_CONFIRM, type AreaJob } from "@/lib/area-jobs";
import { CatalogApiError, deleteAreaJobApi } from "@/lib/catalog-api";
import { cn } from "@/lib/utils";

export function DeleteDiscoveryJobButton({
  job,
  organizationId,
  redirectTo,
  onDeleted,
  className,
}: {
  job: AreaJob;
  organizationId: string;
  redirectTo?: string;
  onDeleted?: () => void;
  className?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canDeleteDiscoveryJob(job.status)) {
    return null;
  }

  async function confirmDelete() {
    setBusy(true);
    setError(null);
    try {
      await deleteAreaJobApi(job.id, organizationId);
      setOpen(false);
      onDeleted?.();
      if (redirectTo) {
        router.push(redirectTo);
      }
    } catch (caught) {
      const message =
        caught instanceof CatalogApiError ? caught.message : "Could not delete this discovery job.";
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button type="button" variant="outline" size="sm" className={cn(className)}>
          Delete
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-6 shadow-lg">
          <Dialog.Title className="text-lg font-medium">Delete this discovery job permanently?</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">
            {DISCOVERY_JOB_DELETE_CONFIRM} Existing catalogues created from selected venues are not deleted.
          </Dialog.Description>
          {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button type="button" variant="outline" disabled={busy}>
                Cancel
              </Button>
            </Dialog.Close>
            <Button type="button" variant="destructive" onClick={confirmDelete} disabled={busy}>
              {busy ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
