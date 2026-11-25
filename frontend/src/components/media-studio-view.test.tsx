import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MediaStudioView } from "@/components/media-studio-view";
import type { MediaStudioResponse } from "@/lib/media-types";

const studio: MediaStudioResponse = {
  catalogue_id: "cat_1",
  restaurant_name: "Harbor Spice",
  source_head_revision: 1,
  source_state_hash: "abc",
  items: [
    {
      path: "menus[0].categories[0].items[0].image_url",
      name: "Chicken Biryani",
      description: "Fragrant basmati rice cooked with chicken, spices, onions and herbs.",
      category_name: "Mains",
      image_url: null,
      has_usable_image: false,
      active_job_id: null,
      active_candidate_id: null,
    },
    {
      path: "menus[0].categories[0].items[1].image_url",
      name: "Naan",
      description: "Tandoor bread.",
      category_name: "Mains",
      image_url: "/catalogue-assets/cat_1/naan.png",
      has_usable_image: true,
      active_job_id: "job_1",
      active_candidate_id: "cand_1",
    },
  ],
  references: [
    {
      path: "menus[0].categories[0].items[1].image_url",
      image_url: "/catalogue-assets/cat_1/naan.png",
      name: "Naan",
      category_name: "Mains",
      reason: "same_category",
    },
  ],
  jobs: [
    {
      id: "job_1",
      catalogue_id: "cat_1",
      organization_id: "org_1",
      path: "menus[0].categories[0].items[1].image_url",
      operation: "enhance",
      status: "READY",
      prompt: null,
      proposal_id: null,
      source_head_revision: 1,
      source_state_hash: "abc",
      source_ref: "/catalogue-assets/cat_1/naan.png",
      original_artifact_id: "orig_1",
      active_candidate_id: "cand_1",
      candidates: [
        {
          id: "cand_1",
          parent_id: null,
          operation: "enhance",
          prompt: null,
          artifact_id: "art_1",
          content_type: "image/png",
          media_kind: "image",
          provider: "local.v1",
          created_at: "2026-08-21T00:00:00Z",
        },
      ],
      reference_paths: [],
      error: null,
      idempotent_replay: false,
      created_at: "2026-08-21T00:00:00Z",
      updated_at: "2026-08-21T00:00:00Z",
    },
  ],
  handoff_path: "menus[0].categories[0].items[0].image_url",
  handoff_check_id: "missing_item_image",
};

describe("MediaStudioView", () => {
  it("renders missing-image workflow with references and generate action", () => {
    const html = renderToStaticMarkup(
      <MediaStudioView
        catalogueId="cat_1"
        organizationId="org_1"
        studio={studio}
        selectedPath="menus[0].categories[0].items[0].image_url"
        tab="images"
        operation="generate_image"
        prompt=""
        generating={false}
        error={null}
        onSelectPath={() => undefined}
        onTab={() => undefined}
        onOperation={() => undefined}
        onPrompt={() => undefined}
        onGenerate={() => undefined}
        onAssist={() => undefined}
        onRevert={() => undefined}
      />,
    );
    expect(html).toContain("Chicken Biryani");
    expect(html).toContain("Fragrant basmati rice");
    expect(html).toContain("AI Image Improvement");
    expect(html).toContain("Generate Image");
    expect(html).toContain("AI Edit");
    expect(html).toContain("Tell Baba what you want to change");
    expect(html).toContain("Restaurant reference images");
    expect(html).toContain("Before");
    expect(html).toContain("After");
    expect(html).toContain("No source image.");
    expect(html).toContain("GIF Creation");
    expect(html).not.toContain("AI video");
    expect(html).not.toContain("Generate video");
  });

  it("renders before/after, revision history, GIF Creation tab, and revert", () => {
    const html = renderToStaticMarkup(
      <MediaStudioView
        catalogueId="cat_1"
        organizationId="org_1"
        studio={studio}
        selectedPath="menus[0].categories[0].items[1].image_url"
        tab="gifs"
        operation="enhance"
        prompt="Create a short animated GIF of the dish."
        generating
        error="AI image generation is temporarily unavailable. Please try again."
        onSelectPath={() => undefined}
        onTab={() => undefined}
        onOperation={() => undefined}
        onGenerate={() => undefined}
        onAssist={() => undefined}
        onRevert={() => undefined}
        onPrompt={() => undefined}
      />,
    );
    expect(html).toContain("GIF Creation");
    expect(html).toContain("GIF preview");
    expect(html).toContain("short animated GIF");
    expect(html).toContain("not AI video");
    expect(html).not.toContain(">Videos<");
    expect(html).not.toContain("Generate video");
    expect(html).toContain("Generating…");
    expect(html).toContain("Revert");
    expect(html).toContain("Revision history");
    expect(html).toContain("Enhance");
    expect(html).toContain("AI image generation is temporarily unavailable. Please try again.");
    expect(html).not.toContain("local.v1");
    expect(html).toContain("/api/catalogues/cat_1/media-artifacts/art_1");
    expect(html).toContain("/api/catalogues/cat_1/media-artifacts/orig_1");
    const idle = renderToStaticMarkup(
      <MediaStudioView
        catalogueId="cat_1"
        organizationId="org_1"
        studio={studio}
        selectedPath="menus[0].categories[0].items[1].image_url"
        tab="gifs"
        operation="image_to_video"
        prompt=""
        generating={false}
        error={null}
        onSelectPath={() => undefined}
        onTab={() => undefined}
        onOperation={() => undefined}
        onGenerate={() => undefined}
        onAssist={() => undefined}
        onRevert={() => undefined}
        onPrompt={() => undefined}
      />,
    );
    expect(idle).toContain("Create GIF");
    expect(idle).not.toContain("Prompt assistance");
  });

  it("does not show a reverted candidate as the active after pane", () => {
    const reverted: MediaStudioResponse = {
      ...studio,
      items: studio.items.map((row) =>
        row.path === "menus[0].categories[0].items[1].image_url"
          ? { ...row, active_job_id: null, active_candidate_id: null }
          : row,
      ),
      jobs: studio.jobs.map((job) => ({ ...job, active_candidate_id: null })),
    };
    const html = renderToStaticMarkup(
      <MediaStudioView
        catalogueId="cat_1"
        organizationId="org_1"
        studio={reverted}
        selectedPath="menus[0].categories[0].items[1].image_url"
        tab="images"
        operation="enhance"
        prompt=""
        generating={false}
        error={null}
        onSelectPath={() => undefined}
        onTab={() => undefined}
        onOperation={() => undefined}
        onPrompt={() => undefined}
        onGenerate={() => undefined}
        onAssist={() => undefined}
        onRevert={() => undefined}
      />,
    );
    expect(html).toContain("Remove Background");
    expect(html).toContain("Generate Background");
    expect(html).toContain("Cleanup");
    expect(html).toContain("No generated candidate yet");
    expect(html).not.toContain("/api/catalogues/cat_1/media-artifacts/art_1");
  });

  it("presents a Vela-style tool rail and enhance workspace without applying catalogue photos", () => {
    const html = renderToStaticMarkup(
      <MediaStudioView
        catalogueId="cat_1"
        organizationId="org_1"
        studio={studio}
        selectedPath="menus[0].categories[0].items[1].image_url"
        tab="images"
        operation="enhance"
        prompt=""
        generating={false}
        error={null}
        onSelectPath={() => undefined}
        onTab={() => undefined}
        onOperation={() => undefined}
        onPrompt={() => undefined}
        onGenerate={() => undefined}
        onAssist={() => undefined}
        onRevert={() => undefined}
      />,
    );
    expect(html).toContain("AI Enhance");
    expect(html).toContain("Crop");
    expect(html).toContain("Background");
    expect(html).toContain("Apply to catalogue");
    expect(html).toContain("preview-only until you apply");
    expect(html).toContain("Sharpen details");
    expect(html).not.toMatch(/>Save</);
  });
});
