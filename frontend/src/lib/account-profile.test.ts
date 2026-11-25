import { describe, expect, it } from "vitest";
import {
  parseAccountProfile,
  parseNotificationPrefs,
  profileHeadline,
  profileStorageKey,
} from "@/lib/account-profile";

describe("account profile", () => {
  it("keys storage by user id", () => {
    expect(profileStorageKey("user_1")).toBe("hecto-baba-profile:user_1");
  });

  it("parses stored profile fields without inventing values", () => {
    const profile = parseAccountProfile(
      JSON.stringify({ fullName: "Bharath L", role: "Founder", companyName: "CatalogForge", city: "Bengaluru" }),
    );
    expect(profile.fullName).toBe("Bharath L");
    expect(profileHeadline(profile)).toBe("Founder · CatalogForge");
    expect(profile.gstin).toBe("");
  });

  it("falls back when JSON is invalid", () => {
    expect(parseAccountProfile("not-json").fullName).toBe("");
    expect(parseNotificationPrefs(null).catalogueReady).toBe(true);
  });
});
