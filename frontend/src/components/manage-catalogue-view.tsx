"use client";

import { TrashIcon } from "@radix-ui/react-icons";
import Link from "next/link";
import { useMemo, useState } from "react";
import { CatalogueImage } from "@/components/catalogue-image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyCatalogueMutationApi } from "@/lib/catalog-api";
import { CatalogApiError } from "@/lib/catalog-api-error";
import type { StoredCatalogue } from "@/lib/catalog-types";
import {
  formatPrice,
  hasProductImage,
  identifyCatalogue,
  isItemAvailable,
  matchesQuery,
  nextAvailableLabel,
  sellingAmount,
  sourceItemId,
  type IdentifiedCategory,
  type IdentifiedItem,
} from "@/lib/catalogue-menu";
import type { CatalogueMutationDraft } from "@/lib/manage-catalogue-ui";
import { catalogueMediaHref } from "@/lib/media-ui";
import { cn } from "@/lib/utils";

function mutationItemId(item: IdentifiedItem): string | undefined {
  if (item.item_id?.trim()) {
    return item.item_id.trim();
  }
  const source = sourceItemId(item);
  return source ?? undefined;
}

function parseLabels(text: string): string[] {
  return text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function labelsText(item: IdentifiedItem): string {
  return (item.labels || []).join(", ");
}

type ProductForm = {
  name: string;
  price: string;
  description: string;
  categoryName: string;
  labels: string;
};

function emptyForm(categoryName = ""): ProductForm {
  return { name: "", price: "", description: "", categoryName, labels: "" };
}

export function ManageCatalogueView({
  entry,
  organizationId,
  onUpdated,
}: {
  entry: StoredCatalogue;
  organizationId: string;
  onUpdated: (row: StoredCatalogue) => void;
}) {
  const categories = useMemo(
    () => identifyCatalogue(entry.result.categories || []),
    [entry.result.categories],
  );
  const categoryNames = useMemo(() => categories.map((row) => row.name).filter(Boolean), [categories]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addForm, setAddForm] = useState<ProductForm>(() => emptyForm(categoryNames[0] || ""));
  const [editing, setEditing] = useState<{ item: IdentifiedItem; category: IdentifiedCategory } | null>(null);
  const [editForm, setEditForm] = useState<ProductForm>(() => emptyForm());

  const filtered = useMemo(() => {
    const needle = query.trim();
    return categories
      .map((category) => ({
        ...category,
        items: category.items.filter((item) => matchesQuery(item, category.name, needle)),
      }))
      .filter((category) => category.items.length > 0 || !needle);
  }, [categories, query]);

  async function runMutation(draft: CatalogueMutationDraft, itemId?: string) {
    if (entry.headRevision == null || !entry.stateHash) {
      setError("Catalogue revision is unavailable. Reload this page and try again.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await applyCatalogueMutationApi(entry.id, organizationId, {
        draft,
        item_id: itemId ?? null,
        source_head_revision: entry.headRevision,
        source_state_hash: entry.stateHash,
      });
      onUpdated(updated);
      return updated;
    } catch (exc) {
      const message = exc instanceof CatalogApiError ? exc.message : "Could not update this catalogue.";
      setError(message);
      throw exc;
    } finally {
      setBusy(false);
    }
  }

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    const price = Number(addForm.price.replace(/[^\d.]/g, ""));
    if (!addForm.name.trim() || !addForm.categoryName.trim() || !Number.isFinite(price) || price <= 0) {
      setError("Name, category, and a valid price are required.");
      return;
    }
    await runMutation({
      operation: "add_item",
      item_name: addForm.name.trim(),
      category_name: addForm.categoryName.trim(),
      price,
      description: addForm.description.trim() || null,
    });
    setAdding(false);
    setAddForm(emptyForm(categoryNames[0] || ""));
  }

  async function handleEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!editing) {
      return;
    }
    const { item, category } = editing;
    const itemId = mutationItemId(item);
    let currentName = item.name;
    const price = Number(editForm.price.replace(/[^\d.]/g, ""));
    const nextLabels = parseLabels(editForm.labels);
    const prevLabels = parseLabels(labelsText(item));

    if (editForm.name.trim() && editForm.name.trim() !== item.name) {
      await runMutation(
        {
          operation: "rename_item",
          item_name: currentName,
          category_name: category.name,
          new_item_name: editForm.name.trim(),
        },
        itemId,
      );
      currentName = editForm.name.trim();
    }
    const base = { item_name: currentName, category_name: category.name };
    if (Number.isFinite(price) && price > 0 && price !== sellingAmount(item)) {
      await runMutation({ operation: "change_price", ...base, price }, itemId);
    }
    if (editForm.description.trim() !== (item.description || "").trim()) {
      await runMutation(
        { operation: "update_description", ...base, description: editForm.description.trim() },
        itemId,
      );
    }
    if (
      nextLabels.join("|") !== prevLabels.join("|") &&
      (nextLabels.length > 0 || prevLabels.length > 0)
    ) {
      await runMutation({ operation: "update_labels", ...base, labels: nextLabels }, itemId);
    }
    if (editForm.categoryName.trim() && editForm.categoryName.trim() !== category.name) {
      await runMutation(
        {
          operation: "move_item",
          ...base,
          target_category_name: editForm.categoryName.trim(),
        },
        itemId,
      );
    }
    setEditing(null);
  }

  async function handleRemove(item: IdentifiedItem, category: IdentifiedCategory) {
    const ok = globalThis.confirm(
      `Remove "${item.name}" from ${category.name}? This cannot be undone except via edit history rollback.`,
    );
    if (!ok) {
      return;
    }
    await runMutation(
      { operation: "remove_item", item_name: item.name, category_name: category.name },
      mutationItemId(item),
    );
  }

  function openEdit(item: IdentifiedItem, category: IdentifiedCategory) {
    setEditing({ item, category });
    setEditForm({
      name: item.name,
      price: String(sellingAmount(item) || ""),
      description: item.description || "",
      categoryName: category.name,
      labels: labelsText(item),
    });
    setError(null);
  }

  return (
    <section className="space-y-6" aria-busy={busy}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Manage Catalogue</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Direct owner edits apply immediately using the same catalogue mutation and edit history pipeline as
            confirmed Baba AI changes. AI improvement proposals remain a separate review workflow.
          </p>
        </div>
        <Button type="button" onClick={() => setAdding(true)} disabled={busy || categoryNames.length === 0}>
          + Add Product
        </Button>
      </div>

      {busy ? (
        <p
          className="rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground"
          role="status"
          aria-live="polite"
        >
          Saving & re-grading… Your change is being applied. Please wait and do not click Save again.
        </p>
      ) : null}

      {error ? <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p> : null}

      <div>
        <Label htmlFor="manage-search">Search products</Label>
        <Input
          id="manage-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name, category, or description"
          className="mt-1 max-w-md"
        />
      </div>

      <div className="space-y-6">
        {filtered.map((category) => (
          <div key={category.key} className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{category.name}</h3>
            <ul className="divide-y divide-border rounded-xl border border-border bg-card">
              {category.items.map((item) => {
                const availability = nextAvailableLabel(item);
                const available = isItemAvailable(item);
                return (
                  <li key={item.key} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <p className="font-medium text-foreground">{item.name}</p>
                        <p className="text-sm font-semibold text-foreground">
                          {formatPrice(sellingAmount(item)) || "No price"}
                        </p>
                        {!available || availability ? (
                          <span className="text-xs text-muted-foreground">Unavailable</span>
                        ) : null}
                      </div>
                      {item.description ? <p className="text-sm text-muted-foreground">{item.description}</p> : null}
                      {item.labels?.length ? (
                        <p className="text-xs text-muted-foreground">Tags: {item.labels.join(", ")}</p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-10 w-10"
                        disabled={busy}
                        aria-label="Edit product"
                        onClick={() => openEdit(item, category)}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src="/icons/manage-edit.jpg"
                          alt=""
                          aria-hidden
                          className="h-6 w-6 object-contain dark:invert"
                        />
                      </Button>
                      <Button asChild variant="ghost" size="icon" className="h-10 w-10">
                        <Link href={catalogueMediaHref(entry.id)} aria-label="Manage product image">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src="/icons/manage-image-edit.png"
                            alt=""
                            aria-hidden
                            className="h-6 w-6 object-contain dark:invert"
                          />
                        </Link>
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-10 w-10 text-destructive hover:text-destructive"
                        disabled={busy}
                        aria-label="Remove product"
                        onClick={() => void handleRemove(item, category)}
                      >
                        <TrashIcon className="h-6 w-6" />
                      </Button>
                    </div>
                    <Link
                      href={catalogueMediaHref(entry.id)}
                      className="shrink-0 overflow-hidden rounded-md border border-border"
                      aria-label={`${item.name} image`}
                    >
                      <CatalogueImage
                        src={hasProductImage(item) ? item.image_url : null}
                        alt={item.name}
                        className="h-20 w-20 object-cover"
                        fallbackClassName="h-20 w-20"
                      />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {filtered.every((category) => category.items.length === 0) ? (
          <p className="text-sm text-muted-foreground">No products match this search.</p>
        ) : null}
      </div>

      {adding ? (
        <form onSubmit={(event) => void handleAdd(event)} className="space-y-4 rounded-xl border border-border bg-card p-4">
          <h3 className="font-medium">Add product</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="add-name">Name</Label>
              <Input id="add-name" value={addForm.name} onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} required />
            </div>
            <div>
              <Label htmlFor="add-price">Price (₹)</Label>
              <Input id="add-price" value={addForm.price} onChange={(e) => setAddForm({ ...addForm, price: e.target.value })} required />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="add-category">Category</Label>
              <select
                id="add-category"
                value={addForm.categoryName}
                onChange={(e) => setAddForm({ ...addForm, categoryName: e.target.value })}
                className={cn("mt-1 flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm")}
              >
                {categoryNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="add-description">Description</Label>
              <Input
                id="add-description"
                value={addForm.description}
                onChange={(e) => setAddForm({ ...addForm, description: e.target.value })}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving & re-grading…" : "Save product"}
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}

      {editing ? (
        <form onSubmit={(event) => void handleEdit(event)} className="space-y-4 rounded-xl border border-border bg-card p-4">
          <h3 className="font-medium">Edit product</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="edit-name">Name</Label>
              <Input id="edit-name" value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} required />
            </div>
            <div>
              <Label htmlFor="edit-price">Price (₹)</Label>
              <Input id="edit-price" value={editForm.price} onChange={(e) => setEditForm({ ...editForm, price: e.target.value })} required />
            </div>
            <div>
              <Label htmlFor="edit-category">Category</Label>
              <select
                id="edit-category"
                value={editForm.categoryName}
                onChange={(e) => setEditForm({ ...editForm, categoryName: e.target.value })}
                className={cn("mt-1 flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm")}
              >
                {categoryNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="edit-labels">Tags (comma-separated)</Label>
              <Input id="edit-labels" value={editForm.labels} onChange={(e) => setEditForm({ ...editForm, labels: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="edit-description">Description</Label>
              <Input
                id="edit-description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Product images are updated from{" "}
            <Link href={catalogueMediaHref(entry.id)} className="underline">
              Generated Media
            </Link>
            . Availability is shown from scraped data and cannot be edited here.
          </p>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving & re-grading…" : "Save changes"}
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
