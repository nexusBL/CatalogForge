import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BabaAiDock } from "@/components/baba-ai-dock";
import { babaAiHref, catalogueAssistantHref } from "@/lib/assistant-ui";

describe("compact Baba AI dock", () => {
  it("renders a compact launcher rather than a full-page chat", () => {
    const html = renderToStaticMarkup(<BabaAiDock catalogueId="cat_1" />);
    expect(html).toContain("Baba AI");
    expect(html).toContain("Open Baba AI");
    expect(html).not.toContain("Choose a catalogue to start");
  });

  it("keeps global Baba AI catalogue context on the existing route", () => {
    expect(babaAiHref("cat_1")).toBe("/baba-ai?catalogue=cat_1");
    expect(catalogueAssistantHref("cat_1")).toBe("/catalogues/cat_1/assistant");
  });
});
