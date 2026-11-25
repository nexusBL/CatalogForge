"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { GradeExplanation, GradeFinding, GradeLetter } from "@/lib/grade-types";
import {
  checkTitle,
  findingSummary,
  formatMeasuredValue,
  gradeHeadline,
  letterBadgeClass,
  resolveFindingProducts,
  sectionOperatorLabel,
  type AffectedProduct,
} from "@/lib/grade-ui";
import { catalogueImprovementsHref, isSupportedImprovementCheck } from "@/lib/improvement-ui";
import { catalogueMediaHref } from "@/lib/media-ui";
import { cn } from "@/lib/utils";

const PREVIEW_COUNT = 8;

function itemStatus(checkId: string): string {
  if (checkId === "category_count_mismatch") {
    return "Declared item count does not match listed items";
  }
  if (checkId.includes("repeated")) {
    return "Same description as another item";
  }
  if (checkId.includes("description")) {
    return "Description missing";
  }
  if (checkId.includes("image")) {
    return "Photo needs improvement";
  }
  if (checkId.includes("label")) {
    return "Labels missing";
  }
  return "Needs review";
}

function ProductRow({
  product,
  status,
  catalogueId,
  checkId,
}: {
  product: AffectedProduct;
  status: string;
  catalogueId?: string;
  checkId: string;
}) {
  const imageAction = Boolean(catalogueId) && checkId.includes("image");
  const descriptionAction = Boolean(catalogueId) && isSupportedImprovementCheck(checkId) && !imageAction;
  const imageHref = product.path.includes("image") ? product.path : `${product.path}.image_url`;
  return (
    <li className="flex items-center gap-3 rounded-md border border-border px-3 py-2">
      {product.imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={product.imageUrl} alt="" className="h-12 w-12 rounded object-cover" />
      ) : (
        <span className="flex h-12 w-12 items-center justify-center rounded bg-muted text-[10px] text-muted-foreground">
          No photo
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{product.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {product.category} · {status}
        </p>
        {product.description && checkId.includes("repeated") ? (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{product.description}</p>
        ) : null}
      </div>
      {descriptionAction && catalogueId ? (
        <Button type="button" size="sm" variant="outline" asChild>
          <Link href={catalogueImprovementsHref(catalogueId, checkId)}>Improve with AI</Link>
        </Button>
      ) : null}
      {imageAction && catalogueId ? (
        <Button type="button" size="sm" variant="outline" asChild>
          <Link href={catalogueMediaHref(catalogueId, { path: imageHref })}>Improve image</Link>
        </Button>
      ) : null}
    </li>
  );
}

function FindingCard({
  finding,
  catalogueId,
  catalogue,
}: {
  finding: GradeFinding;
  catalogueId?: string;
  catalogue?: CatalogCreateResponse | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const products = resolveFindingProducts(finding, catalogue);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return products;
    }
    return products.filter(
      (row) => row.name.toLowerCase().includes(needle) || row.category.toLowerCase().includes(needle),
    );
  }, [products, query]);
  const visible = expanded ? filtered : filtered.slice(0, PREVIEW_COUNT);
  const canPropose = Boolean(catalogueId) && isSupportedImprovementCheck(finding.check_id);
  const imageFinding = finding.check_id.includes("image");
  const measured = formatMeasuredValue(finding.evidence.measured_value);
  const declared = finding.evidence.details.declared;
  const actual = finding.evidence.details.actual;
  return (
    <article className="space-y-3 rounded-lg border border-border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-medium">{checkTitle(finding.check_id)}</h4>
          <p className="mt-1 text-sm text-muted-foreground">{findingSummary(finding, products)}</p>
          {measured && finding.check_id === "description_coverage" ? (
            <p className="mt-1 text-sm text-muted-foreground">
              {measured} of items currently have descriptions. Recommended: add descriptions to at least 70% of items.
            </p>
          ) : null}
          {finding.check_id === "category_count_mismatch" && (declared != null || actual != null) ? (
            <p className="mt-1 text-sm text-muted-foreground">
              Declared items: {String(declared ?? "—")} · Actual items: {String(actual ?? "—")}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {products.length ? (
            <Button type="button" variant="outline" size="sm" onClick={() => setExpanded((value) => !value)}>
              {expanded ? "Show fewer" : `View ${products.length} ${products.length === 1 ? "item" : "items"}`}
            </Button>
          ) : null}
          {canPropose && catalogueId ? (
            <Button type="button" variant="outline" size="sm" asChild>
              <Link href={catalogueImprovementsHref(catalogueId, finding.check_id)}>
                {imageFinding ? "Improve images" : "Improve with AI"}
              </Link>
            </Button>
          ) : null}
          {imageFinding && catalogueId && products[0] ? (
            <Button type="button" variant="outline" size="sm" asChild>
              <Link href={catalogueMediaHref(catalogueId, { path: `${products[0].path}.image_url` })}>
                Improve image
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
      {products.length > 6 ? (
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search affected items"
          aria-label="Search affected items"
        />
      ) : null}
      {visible.length ? (
        <ul className="space-y-2">
          {visible.map((product) => (
            <ProductRow
              key={product.path}
              product={product}
              status={itemStatus(finding.check_id)}
              catalogueId={catalogueId}
              checkId={finding.check_id}
            />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{finding.recommendation?.action || finding.why}</p>
      )}
      {filtered.length > PREVIEW_COUNT && !expanded ? (
        <button type="button" className="text-sm underline" onClick={() => setExpanded(true)}>
          View all {filtered.length}
        </button>
      ) : null}
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">Technical details</summary>
        <p className="mt-2">{finding.why}</p>
      </details>
    </article>
  );
}

export function GradeExplanationView({
  explanation,
  onGrade,
  grading = false,
  error = null,
  catalogueId,
  catalogue = null,
}: {
  explanation: GradeExplanation | null;
  onGrade?: () => void;
  grading?: boolean;
  error?: string | null;
  catalogueId?: string;
  catalogue?: CatalogCreateResponse | null;
}) {
  const topFinding = explanation?.fix_first
    ? explanation.findings.find((row) => row.finding_id === explanation.fix_first?.finding_id)
    : explanation?.findings[0];
  const topProducts = topFinding ? resolveFindingProducts(topFinding, catalogue) : [];

  return (
    <section className="space-y-5 rounded-xl border border-border bg-card p-5 text-card-foreground">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Catalogue quality</h2>
          <p className="text-sm text-muted-foreground">What Baba found in this catalogue, in plain language.</p>
        </div>
        {onGrade ? (
          <Button type="button" onClick={onGrade} disabled={grading}>
            {grading ? "Grading…" : explanation ? "Re-grade this catalogue" : "Grade this catalogue"}
          </Button>
        ) : null}
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!explanation ? (
        <p className="text-sm text-muted-foreground">No completed grade for this catalogue revision.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-5">
            <div
              className={cn(
                "flex h-20 w-20 flex-col items-center justify-center rounded-xl text-3xl font-semibold",
                letterBadgeClass(explanation.overall_grade),
              )}
            >
              {explanation.overall_grade}
            </div>
            <div>
              <p className="text-sm text-muted-foreground">{Math.round(explanation.overall_score)} / 100</p>
              <p className="mt-1 text-base font-medium">{gradeHeadline(explanation.overall_grade)}</p>
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium">Quality areas</h3>
            <ul className="grid gap-2 sm:grid-cols-3">
              {explanation.section_grades.map((section) => (
                <li key={section.section} className="rounded-lg border border-border p-3">
                  <p className="text-xs text-muted-foreground">{sectionOperatorLabel(section.section, section.label)}</p>
                  <p className="mt-1 text-lg font-medium">{section.letter}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded bg-muted">
                    <div className="h-full bg-foreground" style={{ width: `${Math.max(0, Math.min(100, section.score))}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{Math.round(section.score)}%</p>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-lg border border-border bg-background p-4">
            <h3 className="text-sm font-medium">Biggest opportunity</h3>
            {topFinding ? (
              <div className="mt-2 space-y-3">
                <p className="text-sm">{findingSummary(topFinding, topProducts)}</p>
                {catalogueId ? (
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" size="sm" asChild>
                      <Link href={`#finding-${topFinding.finding_id}`}>
                        View {topProducts.length || topFinding.evidence.affected_count} items
                      </Link>
                    </Button>
                    {isSupportedImprovementCheck(topFinding.check_id) ? (
                      <Button type="button" size="sm" asChild>
                        <Link href={catalogueImprovementsHref(catalogueId, topFinding.check_id)}>Improve with AI</Link>
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">No actionable findings for this revision.</p>
            )}
          </div>
          <div className="space-y-3">
            <h3 className="text-sm font-medium">What is lowering your grade?</h3>
            {explanation.findings.length === 0 ? (
              <p className="text-sm text-muted-foreground">No failing evidence was recorded.</p>
            ) : (
              explanation.findings.map((finding) => (
                <div key={finding.finding_id} id={`finding-${finding.finding_id}`}>
                  <FindingCard finding={finding} catalogueId={catalogueId} catalogue={catalogue} />
                </div>
              ))
            )}
          </div>
        </>
      )}
    </section>
  );
}
