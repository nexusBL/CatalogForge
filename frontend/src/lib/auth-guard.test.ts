import { describe, expect, it } from "vitest";
import { isAuthenticatedSession } from "@/lib/auth-guard";

describe("protected dashboard", () => {
  it("rejects missing sessions", () => {
    expect(isAuthenticatedSession(null)).toBe(false);
    expect(isAuthenticatedSession({})).toBe(false);
  });

  it("accepts a Better Auth session user", () => {
    expect(isAuthenticatedSession({ user: { id: "user_1", email: "owner@example.com" } })).toBe(true);
  });
});
