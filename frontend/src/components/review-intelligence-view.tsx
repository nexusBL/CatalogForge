import { Button } from "@/components/ui/button";
import type { ReviewIntelligence, ReviewListResponse } from "@/lib/review-types";

function targetLabel(value: string | undefined): string {
  if (value === "product_item") {
    return "Product / item";
  }
  if (value === "catalogue_menu") {
    return "Catalogue / menu";
  }
  if (value === "website_ux") {
    return "Website / UX";
  }
  if (value === "restaurant_service") {
    return "Restaurant / service";
  }
  return "Other / unknown";
}

export function ReviewIntelligenceView({
  reviews,
  intelligence,
  error,
  loading,
  body,
  rating,
  collecting,
  analyzing,
  onBodyChange,
  onRatingChange,
  onCollect,
  onAnalyze,
  onPrevPage,
  onNextPage,
  organizationId,
}: {
  reviews: ReviewListResponse | null;
  intelligence: ReviewIntelligence | null;
  error: string | null;
  loading: boolean;
  body: string;
  rating: string;
  collecting: boolean;
  analyzing: boolean;
  onBodyChange: (value: string) => void;
  onRatingChange: (value: string) => void;
  onCollect: () => void;
  onAnalyze: () => void;
  onPrevPage?: () => void;
  onNextPage?: () => void;
  organizationId?: string;
}) {
  const current = intelligence?.status === "READY";
  const stale = intelligence?.status === "STALE";
  const failed = intelligence?.status === "FAILED";
  const generating = intelligence?.status === "GENERATING";
  const hasPrev = (reviews?.offset ?? 0) > 0;
  const hasNext = (reviews?.offset ?? 0) + (reviews?.reviews.length ?? 0) < (reviews?.total ?? 0);
  const complaints = current
    ? intelligence.observations.filter((row) => row.recurrence_status === "recurring_complaint")
    : [];
  const themes = current
    ? intelligence.observations.filter((row) => row.positive_theme_status === "positive_theme")
    : [];

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Customer feedback</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          First-party customer feedback intelligence only. Catalogue content is not changed. Recommendations are
          inspect-only.
        </p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <form
        className="space-y-3 rounded-lg border border-border p-4"
        onSubmit={(event) => {
          event.preventDefault();
          onCollect();
        }}
      >
        <p className="text-sm font-medium">Operator supplied text (test ingest)</p>
        <label className="block text-sm font-medium" htmlFor="review-body">
          Review text
        </label>
        <textarea
          id="review-body"
          className="min-h-24 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          value={body}
          onChange={(event) => onBodyChange(event.target.value)}
        />
        <label className="block text-sm font-medium" htmlFor="review-rating">
          Observed rating (optional)
        </label>
        <input
          id="review-rating"
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          value={rating}
          onChange={(event) => onRatingChange(event.target.value)}
        />
        <Button type="submit" disabled={collecting || !body.trim()}>
          {collecting ? "Saving…" : "Store supplied review"}
        </Button>
      </form>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Stored customer feedback</h2>
          <Button type="button" variant="outline" onClick={onAnalyze} disabled={analyzing || generating}>
            {analyzing || generating ? "Analyzing…" : "Analyze reviews"}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Total: {reviews?.total ?? 0}</p>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading reviews…</p>
        ) : !reviews?.reviews.length ? (
          <p className="text-sm text-muted-foreground">No customer feedback stored for this catalogue.</p>
        ) : (
          <ul className="space-y-2">
            {reviews.reviews.map((row) => (
              <li key={row.id} className="rounded-md border border-border p-3 text-sm">
                <p>{row.body}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Source: {row.source}
                  {row.observed_rating != null ? ` · Rating: ${row.observed_rating}` : ""}
                  {row.created_at ? ` · ${row.created_at}` : ""}
                </p>
                {row.photo_id && organizationId ? (
                  <a
                    className="mt-2 inline-block text-xs underline"
                    href={`/api/catalogues/${encodeURIComponent(row.catalogue_id)}/customer-feedback-photos/${encodeURIComponent(row.photo_id)}?organization_id=${encodeURIComponent(organizationId)}`}
                  >
                    Evidence photo
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {reviews && reviews.total > reviews.limit ? (
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" disabled={!hasPrev} onClick={onPrevPage}>
              Previous
            </Button>
            <p className="text-xs text-muted-foreground">
              {reviews.offset + 1}–{reviews.offset + reviews.reviews.length} of {reviews.total}
            </p>
            <Button type="button" variant="outline" disabled={!hasNext} onClick={onNextPage}>
              Next
            </Button>
          </div>
        ) : null}
      </div>
      {intelligence ? (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold">Intelligence</h2>
          <p className="text-sm text-muted-foreground">
            Status: {intelligence.status}. Overall polarity: {intelligence.polarity_status}. Recurrence:{" "}
            {intelligence.recurrence_status}. Positive themes: {intelligence.positive_theme_status}.
          </p>
          {stale ? (
            <p className="text-sm text-destructive">
              This analysis is not current. Catalogue or stored reviews changed. Analyze again.
            </p>
          ) : null}
          {generating ? <p className="text-sm text-muted-foreground">Analysis is in progress.</p> : null}
          {intelligence.failure_reason ? <p className="text-sm text-destructive">{intelligence.failure_reason}</p> : null}
          {current ? (
            <>
              {complaints.length ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Recurring complaints</h3>
                  <ul className="space-y-2">
                    {complaints.map((row) => (
                      <li key={`c-${row.observation_id}`} className="rounded-md border border-border p-3 text-sm">
                        {targetLabel(row.target)}
                        {row.item_name ? ` · ${row.item_name}` : ""} · {row.aspect} · {row.review_count} submissions
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {themes.length ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Positive themes</h3>
                  <ul className="space-y-2">
                    {themes.map((row) => (
                      <li key={`t-${row.observation_id}`} className="rounded-md border border-border p-3 text-sm">
                        {targetLabel(row.target)}
                        {row.item_name ? ` · ${row.item_name}` : ""} · {row.aspect} · {row.review_count} submissions
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <ul className="space-y-2">
                {intelligence.observations.map((row) => (
                  <li key={row.observation_id} className="rounded-md border border-border p-3 text-sm">
                    <p>
                      About: {targetLabel(row.target)}
                      {row.item_name ? ` · ${row.item_name}` : ""} · {row.aspect} · {row.polarity} · {row.intent}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {row.review_count} related submission{row.review_count === 1 ? "" : "s"} · {row.recurrence_status}{" "}
                      · linkage {row.linkage_status}
                      {row.request_kind === "improvement_request" ? " · customer requested an improvement" : ""}
                    </p>
                  </li>
                ))}
              </ul>
              <ul className="space-y-2">
                {intelligence.recommendations.map((row) => (
                  <li key={row.recommendation_id} className="rounded-md border border-border p-3 text-sm">
                    <p>{row.action}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {targetLabel(row.target)} · Evidence reviews: {row.evidence_review_ids.length}
                    </p>
                  </li>
                ))}
              </ul>
            </>
          ) : failed ? (
            <p className="text-sm text-muted-foreground">No current recommendations. Retry analysis.</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
