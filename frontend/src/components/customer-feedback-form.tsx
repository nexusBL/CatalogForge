"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { CatalogApiError, submitCustomerFeedbackApi } from "@/lib/catalog-api";

export function CustomerFeedbackForm({
  catalogueId,
  organizationId,
  restaurantName,
}: {
  catalogueId: string;
  organizationId: string;
  restaurantName: string;
}) {
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const [body, setBody] = useState("");
  const [rating, setRating] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setError("Please write your feedback.");
      return;
    }
    const parsed = rating.trim() ? Number(rating) : undefined;
    if (parsed != null && Number.isNaN(parsed)) {
      setError("Rating must be a number.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      await submitCustomerFeedbackApi(catalogueId, organizationId, {
        body: body.trim(),
        externalId: idempotencyKey,
        observedRating: parsed,
        photo,
      });
      setSuccess(true);
      setBody("");
      setRating("");
      setPhoto(null);
      setIdempotencyKey(crypto.randomUUID());
    } catch (caught: unknown) {
      setError(caught instanceof CatalogApiError ? caught.message : "Could not send feedback.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-xl border border-border bg-card p-4 text-card-foreground">
      <h2 className="text-sm font-semibold">Customer feedback</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Feedback for {restaurantName}. You do not need to type the restaurant name. Written feedback is
        required. Photos are optional.
      </p>
      <form className="mt-3 space-y-3" onSubmit={(event) => void onSubmit(event)}>
        <label className="block text-sm font-medium" htmlFor="customer-feedback-body">
          Your feedback
        </label>
        <textarea
          id="customer-feedback-body"
          required
          className="min-h-24 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <label className="block text-sm font-medium" htmlFor="customer-feedback-rating">
          Rating (optional)
        </label>
        <input
          id="customer-feedback-rating"
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          inputMode="decimal"
          value={rating}
          onChange={(event) => setRating(event.target.value)}
        />
        <label className="block text-sm font-medium" htmlFor="customer-feedback-photo">
          Photo (optional)
        </label>
        <input
          id="customer-feedback-photo"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => setPhoto(event.target.files?.[0] || null)}
        />
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {success ? <p className="text-sm text-muted-foreground">Thanks. Your feedback was saved.</p> : null}
        <Button type="submit" disabled={saving || !body.trim()}>
          {saving ? "Sending…" : "Send feedback"}
        </Button>
      </form>
    </section>
  );
}
