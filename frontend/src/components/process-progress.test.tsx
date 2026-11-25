import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProcessProgressBar } from "@/components/process-progress";

describe("ProcessProgressBar", () => {
  it("shows running label and percent", () => {
    const html = renderToStaticMarkup(
      <ProcessProgressBar phase="running" percent={42} runningLabel="Scraping…" />,
    );
    expect(html).toContain("Scraping…");
    expect(html).toContain("42%");
    expect(html).toContain('aria-busy="true"');
  });

  it("shows completed at 100%", () => {
    const html = renderToStaticMarkup(
      <ProcessProgressBar phase="completed" percent={80} completedLabel="Catalogue created" />,
    );
    expect(html).toContain("Catalogue created");
    expect(html).toContain("100%");
  });

  it("shows failed state", () => {
    const html = renderToStaticMarkup(
      <ProcessProgressBar phase="failed" percent={55} failedLabel="Scraping failed" />,
    );
    expect(html).toContain("Scraping failed");
  });
});
