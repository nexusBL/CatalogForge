import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ImprovementPreviewView } from "@/components/improvement-preview-view";
import type { CatalogCreateResponse } from "@/lib/catalog-types";
import type { ImprovementProposal } from "@/lib/improvement-types";

const catalogue: CatalogCreateResponse = {
  extraction_status: "ok",
  restaurant_name: "Demo",
  fssai_number: "1",
  source_url: "https://example.com",
  categories: [
    {
      name: "Mains",
      items: [{ name: "Ghee Rice", description: null, image_url: "https://cdn.example/rice.jpg" }],
    },
  ],
};

const proposal: ImprovementProposal = {
  id: "p1",
  catalogue_id: "cat_1",
  organization_id: "org_1",
  source_head_revision: 1,
  source_state_hash: "abc",
  check_id: "missing_description",
  finding_id: "deterministic:missing_description",
  improvement_version: "improvement.v1",
  status: "READY",
  created_at: "2026-08-21T00:00:00+00:00",
  idempotent_replay: false,
  lines: [
    {
      path: "menus[0].categories[0].items[0].description",
      kind: "description",
      check_id: "missing_description",
      finding_id: "deterministic:missing_description",
      current_value: null,
      proposed_value: "Ghee Rice from the Mains menu.",
      status: "READY",
      failure_reason: null,
      why: "Add descriptions for the 1 items that have none.",
    },
  ],
};

describe("improvement preview UI", () => {
  it("renders current, proposed, why, and preview status without an apply action", () => {
    const html = renderToStaticMarkup(
      <ImprovementPreviewView proposals={[proposal]} catalogue={catalogue} />,
    );
    expect(html).toContain("Current");
    expect(html).toContain("suggestion");
    expect(html).toContain("Why?");
    expect(html).toContain("Preview status: READY");
    expect(html).toContain("Ghee Rice from the Mains menu.");
    expect(html).toContain("No description");
    expect(html).toContain("Ghee Rice");
    expect(html).toContain("Proposed changes");
    expect(html).not.toMatch(/>Apply</i);
    expect(html).not.toMatch(/>Approve</i);
  });

  it("shows apply when the owner callback is provided", () => {
    const html = renderToStaticMarkup(
      <ImprovementPreviewView proposals={[proposal]} catalogue={catalogue} onApply={() => undefined} />,
    );
    expect(html).toMatch(/Replace with this|Replace/);
  });

  it("renders media handoff and labels in the same preview contract", () => {
    const html = renderToStaticMarkup(
      <ImprovementPreviewView
        catalogueId="cat_1"
        catalogue={catalogue}
        proposals={[
          {
            ...proposal,
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
          },
        ]}
      />,
    );
    expect(html).toContain("Current photo needs improvement");
    expect(html).toContain("Phase 7 image/video improvement handoff");
    expect(html).toContain("Improve image");
  });
});
