import { describe, expect, it } from "vitest";
import { catalogueManageHref } from "@/lib/manage-catalogue-ui";

describe("manage catalogue ui", () => {
  it("builds manage catalogue href", () => {
    expect(catalogueManageHref("abc-123")).toBe("/catalogues/abc-123/manage");
  });
});
