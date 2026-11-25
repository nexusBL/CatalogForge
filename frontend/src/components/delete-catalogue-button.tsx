"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CATALOGUE_PERMANENT_DELETE_CONFIRM } from "@/lib/area-jobs";
import { CatalogApiError, deleteCatalogueApi } from "@/lib/catalog-api";
import { removeCatalogue } from "@/lib/catalogue-store";
import type { StoredCatalogue } from "@/lib/catalog-types";
import { venueDisplayName, venueLocation } from "@/lib/restaurant-identity";
import { cn } from "@/lib/utils";

export function DeleteCatalogueButton({
  item,
  organizationId,
  redirectTo,
  onDeleted,
  className,
}: {
  item: StoredCatalogue;
  organizationId: string;
  redirectTo?: string;
  onDeleted?: () => void;
  className?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const name = venueDisplayName(item.result);
  const location = venueLocation(item.result);
  const label = [name, location].filter(Boolean).join(" — ");

  async function confirmDelete() {
    setBusy(true);
    setError(null);
    try {
      await deleteCatalogueApi(item.id, organizationId);
      removeCatalogue(item.id, organizationId);
      setOpen(false);
      onDeleted?.();
      router.refresh();
      if (redirectTo) {
        router.push(redirectTo);
      }
    } catch (caught) {
      const message =
        caught instanceof CatalogApiError ? caught.message : "Could not delete this catalogue.";
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button type="button" variant="outline" size="sm" className={cn(className)}>
          Delete permanently
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-6 shadow-lg">
          <Dialog.Title className="text-lg font-medium">Delete this catalogue permanently?</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">
            {CATALOGUE_PERMANENT_DELETE_CONFIRM}
            <span className="mt-2 block font-medium text-foreground">“{label}”</span>
          </Dialog.Description>
          {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
          <div className="mt-6 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button type="button" variant="outline" disabled={busy}>
                Cancel
              </Button>
            </Dialog.Close>
            <Button type="button" variant="destructive" onClick={confirmDelete} disabled={busy}>
              {busy ? "Deleting…" : "Delete permanently"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
