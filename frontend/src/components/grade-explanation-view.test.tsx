import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GradeExplanationView } from "@/components/grade-explanation-view";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { GradeExplanation } from "@/lib/grade-types";

const catalogue: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Demo",
  fssai_number: "1",
  source_url: "https://example.com",
  categories: [
    {
      name: "Breakfast",
      items: [
        { name: "Veg Grilled Sandwich", description: null, image_url: "https://cdn.example/sandwich.jpg" },
        { name: "Masala Dosa", description: "", image_url: "https://cdn.example/dosa.jpg" },
      ],
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
  overall_why: "Overall grade D (score 52) from persisted grading.v1. The letter is not recalculated by Phase 5.",
  section_grades: [
    { section: "deterministic", label: "Deterministic", letter: "B", score: 80 },
    { section: "nlp", label: "Text", letter: "D", score: 40 },
    { section: "vision", label: "Images", letter: "A", score: 100 },
  ],
  findings: [
    {
      finding_id: "nlp:missing_description",
      section: "nlp",
      check_id: "missing_description",
      severity: "ordinary",
      result: "fail",
      why: "Item description is missing. Affected count: 4.",
      evidence: {
        failed_criterion: "missing_description",
        affected_count: 4,
        affected_field: "description",
        measured_value: null,
        paths: ["menus[0].categories[0].items[0].description", "menus[0].categories[0].items[1].description"],
        details: {},
      },
      recommendation: {
        finding_id: "nlp:missing_description",
        priority: 1,
        action: "Add descriptions for the 4 items that have none.",
        section: "nlp",
        check_id: "missing_description",
        severity: "ordinary",
      },
    },
  ],
  recommendations: [
    {
      finding_id: "nlp:missing_description",
      priority: 1,
      action: "Add descriptions for the 4 items that have none.",
      section: "nlp",
      check_id: "missing_description",
      severity: "ordinary",
    },
  ],
  fix_first: {
    finding_id: "nlp:missing_description",
    priority: 1,
    action: "Add descriptions for the 4 items that have none.",
    section: "nlp",
    check_id: "missing_description",
    severity: "ordinary",
  },
  priority_rule: "hard then ordinary",
  derived: true,
};

describe("grade explanation UI", () => {
  it("explains the grade in operator language and shows the actual products", () => {
    const html = renderToStaticMarkup(
      <GradeExplanationView explanation={explanation} catalogue={catalogue} catalogueId="cat_1" />,
    );
    expect(html).toContain("Catalogue quality");
    expect(html).toContain(">D<");
    expect(html).toContain("Your catalogue needs substantial listing improvements.");
    expect(html).toContain("Catalogue data");
    expect(html).toContain("Descriptions");
    expect(html).toContain("Images");
    expect(html).toContain("Missing descriptions");
    expect(html).toContain("Veg Grilled Sandwich");
    expect(html).toContain("Masala Dosa");
    expect(html).toContain("https://cdn.example/sandwich.jpg");
    expect(html).toContain("What is lowering your grade?");
    expect(html).toContain("Biggest opportunity");
    expect(html).toContain("Technical details");
    expect(html).not.toContain("failed_criterion");
    expect(html).not.toContain("Turn catalogue quality findings into proposed changes");
  });

  it("offers Improve with AI navigation for supported findings and never an apply control", () => {
    const html = renderToStaticMarkup(
      <GradeExplanationView explanation={explanation} catalogueId="cat_1" catalogue={catalogue} />,
    );
    expect(html).toContain("Improve with AI");
    expect(html).toContain("/catalogues/cat_1/improvements?check_id=missing_description");
    expect(html).not.toContain("Preview improvement");
    expect(html).not.toContain("Proposed changes");
    expect(html).not.toMatch(/>Apply</i);
  });

  it("renders a missing-grade state without fabricating findings", () => {
    const html = renderToStaticMarkup(<GradeExplanationView explanation={null} />);
    expect(html).toContain("No completed grade for this catalogue revision.");
    expect(html).not.toContain("What is lowering your grade?");
  });

  it("renders load errors instead of pretending the grade is missing", () => {
    const html = renderToStaticMarkup(
      <GradeExplanationView explanation={null} error="Could not load this catalogue grade." />,
    );
    expect(html).toContain("Could not load this catalogue grade.");
  });
});
