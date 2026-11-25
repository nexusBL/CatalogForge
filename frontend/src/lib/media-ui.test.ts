import { describe, expect, it } from "vitest";
import { imageOperationsForItem, publicMediaError } from "@/lib/media-ui";

describe("media-ui", () => {
  it("maps hosted failures to a safe image message", () => {
    expect(publicMediaError("The media provider rate-limited or exhausted quota.", "images")).toBe(
      "AI image generation is temporarily unavailable. Please try again.",
    );
    expect(publicMediaError("The media provider timed out.", "images")).toBe(
      "AI image generation is temporarily unavailable. Please try again.",
    );
  });

  it("does not call GIF creation AI video", () => {
    expect(publicMediaError("The media provider is unavailable.", "gifs")).toBe(
      "GIF creation is temporarily unavailable. Please try again.",
    );
    expect(publicMediaError("Prompt looks like an instruction injection and was rejected.", "images")).toBe(
      "Prompt looks like an instruction injection and was rejected.",
    );
  });

  it("lists AI Edit with other image operations for items that have photos", () => {
    const labels = imageOperationsForItem(true).map((row) => row.label);
    expect(labels).toEqual([
      "AI Edit",
      "Enhance",
      "Remove Background",
      "Generate Background",
      "Blur",
      "Crop",
      "Expand",
      "Cleanup",
    ]);
  });
});
