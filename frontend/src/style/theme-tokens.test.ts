import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("grayscale theme tokens", () => {
  const css = readFileSync(resolve(process.cwd(), "src/style/globals.css"), "utf8");

  it("uses Radix gray scales and no blue/navy primary", () => {
    expect(css).toContain("--gray-1: #fcfcfc");
    expect(css).toContain("--gray-12: #202020");
    expect(css).not.toContain('@import "@radix-ui/colors/gray.css"');
    expect(css).not.toContain("225 100% 50%");
    expect(css).not.toContain("222.2 84%");
  });

  it("maps light mode to Radix gray surfaces", () => {
    expect(css).toContain("--background: var(--gray-2)");
    expect(css).toContain("--sidebar: var(--gray-3)");
    expect(css).toContain("--header: var(--gray-1)");
    expect(css).toContain("--card: var(--gray-1)");
    expect(css).toContain("--foreground: var(--gray-12)");
  });

  it("maps dark mode to a near-black grayscale interface", () => {
    expect(css).toContain("--background: #000000");
    expect(css).toContain("--sidebar: #050505");
    expect(css).toContain("--header: #000000");
    expect(css).toContain("--card: #0a0a0a");
    expect(css).toContain("--gray-1: #111111");
  });
});
