import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AiImprovementsView } from "@/components/ai-improvements-view";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import { ImprovementPreviewView } from "@/components/improvement-preview-view";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { GradeExplanation } from "@/lib/grade-types";
import type { ImprovementProposal } from "@/lib/improvement-types";

const catalogue: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Demo",
  fssai_number: "1",
  source_url: "https://example.com",
  categories: [
    {
      name: "Breakfast",
      items: [{ name: "Veg Grilled Sandwich", description: null, image_url: "https://cdn.example/sandwich.jpg" }],
    },
  ],
};

const explanation: GradeExplanation = {
  catalogue_id: "cat_1",
  graded_head_revision: 0,
  graded_state_hash: "abc",
  engine_version: "grading.v1",
  explanation_version: "grade_explain.v1",
  overall_grade: "D",
  overall_score: 52,
  overall_why: "Overall grade D",
  section_grades: [],
  findings: [
    {
      finding_id: "nlp:missing_description",
      section: "nlp",
      check_id: "missing_description",
      severity: "ordinary",
      result: "fail",
      why: "Item description is missing.",
      evidence: {
        failed_criterion: "missing_description",
        affected_count: 6,
        affected_field: "description",
        measured_value: null,
        paths: ["menus[0].categories[0].items[0].description"],
        details: {},
      },
      recommendation: {
        finding_id: "nlp:missing_description",
        priority: 1,
        action: "Add descriptions for 6 items.",
        section: "nlp",
        check_id: "missing_description",
        severity: "ordinary",
      },
    },
    {
      finding_id: "deterministic:missing_item_name",
      section: "deterministic",
      check_id: "missing_item_name",
      severity: "hard",
      result: "fail",
      why: "Item name is missing.",
      evidence: {
        failed_criterion: "missing_item_name",
        affected_count: 1,
        affected_field: "name",
        measured_value: null,
        paths: [],
        details: {},
      },
      recommendation: {
        finding_id: "deterministic:missing_item_name",
        priority: 1,
        action: "Add item names.",
        section: "deterministic",
        check_id: "missing_item_name",
        severity: "hard",
      },
    },
  ],
  recommendations: [],
  fix_first: null,
  priority_rule: "hard then ordinary",
  derived: true,
};

function proposal(overrides: Partial<ImprovementProposal> = {}): ImprovementProposal {
  return {
    id: "p1",
    catalogue_id: "cat_1",
    organization_id: "org_1",
    source_head_revision: 1,
    source_state_hash: "abc",
    check_id: "missing_description",
    finding_id: "nlp:missing_description",
    improvement_version: "improvement.v1",
    status: "READY",
    created_at: "2026-08-21T00:00:00+00:00",
    idempotent_replay: false,
    lines: [
      {
        path: "menus[0].categories[0].items[0].description",
        kind: "description",
        check_id: "missing_description",
        finding_id: "nlp:missing_description",
        current_value: null,
        proposed_value: "Ghee Rice from the Mains menu.",
        status: "READY",
        failure_reason: null,
        why: "Add descriptions for the 1 items that have none.",
      },
    ],
    ...overrides,
  };
}

describe("AI Improvements page", () => {
  it("renders operator-facing improvement opportunities without check ids as the heading", () => {
    const html = renderToStaticMarkup(
      <AiImprovementsView explanation={explanation} proposals={[]} onPreview={() => undefined} catalogue={catalogue} />,
    );
    expect(html).toContain("AI Improvements");
    expect(html).toContain("Improve");
    expect(html).toContain("What Baba can improve");
    expect(html).toContain("Missing descriptions");
    expect(html).toContain("Add descriptions for 6 items.");
    expect(html).toContain("6 items affected");
    expect(html).toContain("Missing labels");
    expect(html).toContain("Veg Grilled Sandwich");
    expect(html).not.toContain("missing_item_name");
    expect(html).not.toMatch(/>Apply</i);
    expect(html).not.toMatch(/>Approve</i);
    expect(html).not.toMatch(/Publish/i);
  });

  it("shows empty state when there is no grade", () => {
    const html = renderToStaticMarkup(
      <AiImprovementsView explanation={null} proposals={[]} onPreview={() => undefined} />,
    );
    expect(html).toContain("No AI improvements available");
    expect(html).not.toMatch(/>Improve</);
  });

  it("renders description, labels, price, and media previews on the actual product", () => {
    const html = renderToStaticMarkup(
      <ImprovementPreviewView
        catalogueId="cat_1"
        catalogue={catalogue}
        proposals={[
          proposal(),
          proposal({
            id: "p2",
            check_id: "empty_item_labels",
            lines: [
              {
                path: "menus[0].categories[0].items[0].labels",
                kind: "labels",
                check_id: "empty_item_labels",
                finding_id: "catalogue_state:empty_item_labels",
                current_value: null,
                proposed_value: "VEG",
                proposed_labels: ["VEG"],
                status: "READY",
                failure_reason: null,
                why: "Add catalogue labels.",
              },
            ],
          }),
          proposal({
            id: "p3",
            check_id: "missing_price",
            lines: [
              {
                path: "menus[0].categories[0].items[0].price",
                kind: "item_price",
                check_id: "missing_price",
                finding_id: "deterministic:missing_price",
                current_value: null,
                proposed_value: "249",
                status: "READY",
                failure_reason: null,
                why: "Copy trusted original_price.",
              },
            ],
          }),
          proposal({
            id: "p4",
            check_id: "missing_item_image",
            lines: [
              {
                path: "menus[0].categories[0].items[0].image_url",
                kind: "media_handoff",
                check_id: "missing_item_image",
                finding_id: "deterministic:missing_item_image",
                current_value: null,
                proposed_value: "Phase 7 image/video improvement handoff",
                media_handoff: {
                  phase7_required: true,
                  media_type: "image",
                  capability: "image_improvement",
                  current_ref: null,
                },
                status: "READY",
                failure_reason: null,
                why: "Add images for items that have none.",
              },
            ],
          }),
        ]}
      />,
    );
    expect(html).toContain("Veg Grilled Sandwich");
    expect(html).toContain("Ghee Rice from the Mains menu.");
    expect(html).toContain("No labels");
    expect(html).toContain("VEG");
    expect(html).toContain("249");
    expect(html).toContain("Current photo needs improvement");
    expect(html).toContain("Phase 7 image/video improvement handoff");
    expect(html).toContain("Improve image");
    expect(html).toContain("/catalogues/cat_1/media");
    expect(html).not.toMatch(/>Apply</i);
  });

  it("renders FAILED without fake proposed content", () => {
    const html = renderToStaticMarkup(
      <ImprovementPreviewView
        proposals={[
          proposal({
            status: "FAILED",
            lines: [
              {
                path: "menus[0].categories[0].items[0].description",
                kind: "description",
                check_id: "missing_description",
                finding_id: "nlp:missing_description",
                current_value: null,
                proposed_value: null,
                status: "FAILED",
                failure_reason: "hallucinated ingredients",
                why: "Add descriptions.",
              },
            ],
          }),
        ]}
        onRetry={() => undefined}
      />,
    );
    expect(html).toContain("Preview status: FAILED");
    expect(html).toContain("safely generate this description");
    expect(html).toContain("Retry preview");
    expect(html).not.toMatch(/>Apply</i);
  });

  it("renders STALE with a fresh-preview action", () => {
    const html = renderToStaticMarkup(
      <ImprovementPreviewView proposals={[proposal({ status: "STALE" })]} onRetry={() => undefined} />,
    );
    expect(html).toContain("this preview is stale");
    expect(html).toContain("Generate a fresh preview");
  });
  it("renders inline proposal directly under item aspect row when generated", () => {
    const html = renderToStaticMarkup(
      <AiImprovementsView
        explanation={explanation}
        proposals={[proposal()]}
        onPreview={() => undefined}
        onApply={() => undefined}
        catalogue={catalogue}
      />,
    );
    expect(html).toContain("Veg Grilled Sandwich");
    expect(html).toContain("✨ Baba’s Proposed Description");
    expect(html).toContain("Ghee Rice from the Mains menu.");
    expect(html).toContain("Replace with this");
  });

  it("shows Generating... ONLY on the targeted item path when proposingPath is specified", () => {
    const html = renderToStaticMarkup(
      <AiImprovementsView
        explanation={explanation}
        proposals={[]}
        onPreview={() => undefined}
        proposingCheckId="missing_description"
        proposingPath="menus[0].categories[0].items[0].description"
        catalogue={{
          ...catalogue,
          categories: [
            {
              name: "Breakfast",
              items: [
                { name: "Avacado Lassi", description: null },
                { name: "Apple Cinnamon Lassi", description: null },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain("Avacado Lassi");
    expect(html).toContain("Apple Cinnamon Lassi");
    // Generating... should appear
    expect(html).toContain("Generating…");
    // Improve with AI should still be present for the non-targeted item button
    expect(html).toContain("Improve with AI");
  });
});

describe("catalogue workspace nav", () => {
  it("links Grade and AI Improvements for the same catalogue", () => {
    const html = renderToStaticMarkup(<CatalogueWorkspaceNav catalogueId="cat_1" active="improvements" />);
    expect(html).toContain('href="/catalogues/cat_1"');
    expect(html).toContain('href="/catalogues/cat_1/improvements"');
    expect(html).toContain('href="/catalogues/cat_1/media"');
    expect(html).toContain('href="/catalogues/cat_1/reviews"');
    expect(html).toContain("Grade / AI Improvements");
    expect(html).toContain("Generated Media");
    expect(html).toContain("Reviews");
  });
});
