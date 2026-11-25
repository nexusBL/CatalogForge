import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { BabaAiWorkspace } from "@/components/baba-ai-workspace";
import { CatalogueWorkspaceNav } from "@/components/catalogue-workspace-nav";
import { babaAiHref, catalogueAssistantHref } from "@/lib/assistant-ui";
import type { StoredCatalogue } from "@/lib/catalog-types";

const sample: StoredCatalogue = {
  id: "cat_1",
  organizationId: "org_1",
  createdAt: "2026-01-01T00:00:00Z",
  result: {
    extraction_status: "ok",
    restaurant_name: "The Lassi Pub",
    fssai_number: "1",
    source_url: "https://www.swiggy.com/city/bangalore/the-lassi-pub-rest1",
    platform: "swiggy",
    catalogue_type: "restaurant",
    restaurant: { name: "The Lassi Pub", outlet: "Indiranagar, Bangalore" },
  },
};

describe("Baba AI workspace", () => {
  it("keeps Baba AI off the catalogue workspace tabs", () => {
    const html = renderToStaticMarkup(<CatalogueWorkspaceNav catalogueId="cat_1" active="grade" />);
    expect(html).toContain("/catalogues/cat_1");
    expect(html).toContain("/catalogues/cat_1/improvements");
    expect(html).toContain("/catalogues/cat_1/media");
    expect(html).toContain("/catalogues/cat_1/reviews");
    expect(html).not.toContain("Baba AI");
    expect(html).not.toContain("/catalogues/cat_1/assistant");
    expect(catalogueAssistantHref("cat_1")).toBe("/catalogues/cat_1/assistant");
    expect(babaAiHref("cat_1")).toBe("/baba-ai?catalogue=cat_1");
  });

  it("asks the user to choose a catalogue before calling the assistant", () => {
    const html = renderToStaticMarkup(
      <BabaAiWorkspace
        catalogues={[]}
        selectedId={null}
        onSelectCatalogue={() => undefined}
        messages={[]}
        value=""
        onChange={() => undefined}
        onSend={() => undefined}
        sending={false}
        error={null}
      />,
    );
    expect(html).toContain("Choose a catalogue to start");
    expect(html).toContain("Choose catalogue");
  });

  it("renders suggested prompts for a selected catalogue", () => {
    const html = renderToStaticMarkup(
      <BabaAiWorkspace
        catalogues={[sample]}
        selectedId="cat_1"
        onSelectCatalogue={() => undefined}
        messages={[]}
        value=""
        onChange={() => undefined}
        onSend={() => undefined}
        sending={false}
        error={null}
      />,
    );
    expect(html).toContain("The Lassi Pub");
    expect(html).toContain("Restaurant · Indiranagar, Bangalore");
    expect(html).toContain("Why is my catalogue graded C?");
    expect(html).toContain("What can I help you with?");
  });

  it("renders the reply, unavailable state, and allowlisted action links", () => {
    const onSend = vi.fn();
    const html = renderToStaticMarkup(
      <BabaAiWorkspace
        catalogues={[sample]}
        selectedId="cat_1"
        onSelectCatalogue={() => undefined}
        messages={[
          { id: "u1", role: "user", text: "Why is my catalogue graded C?" },
          {
            id: "a1",
            role: "assistant",
            text: "Your catalogue is graded C.",
            actions: [{ label: "View Grade Details", href: "/catalogues/cat_1" }],
            unavailable: "No completed grade for this catalogue revision.",
          },
        ]}
        value=""
        onChange={() => undefined}
        onSend={onSend}
        sending={false}
        error={null}
      />,
    );
    expect(html).toContain("Your catalogue is graded C.");
    expect(html).toContain("No completed grade for this catalogue revision.");
    expect(html).toContain('href="/catalogues/cat_1"');
    expect(html).toContain("View Grade Details");
    expect(html).toContain("Ask Baba AI about this catalogue");
  });
});
