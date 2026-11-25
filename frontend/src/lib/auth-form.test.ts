import { describe, expect, it } from "vitest";
import {
  authErrorMessage,
  changePasswordErrorMessage,
  validateChangePassword,
  validateSignupPasswords,
  validateUsername,
} from "@/lib/auth-form";

describe("auth form validation", () => {
  it("requires a username between 3 and 30 characters", () => {
    expect(validateUsername("")).toBeTruthy();
    expect(validateUsername("ab")).toBeTruthy();
    expect(validateUsername("owner")).toBeNull();
    expect(validateUsername("a".repeat(31))).toBeTruthy();
  });

  it("rejects mismatched signup passwords", () => {
    expect(validateSignupPasswords("password1", "password2")).toBe("Passwords do not match.");
    expect(validateSignupPasswords("password1", "password1")).toBeNull();
  });

  it("validates change password fields before submit", () => {
    expect(validateChangePassword("", "newpassword", "newpassword")).toBe("Current password is required.");
    expect(validateChangePassword("current1", "short", "short")).toBe("Password must be at least 8 characters.");
    expect(validateChangePassword("current1", "newpassword1", "newpassword2")).toBe("Passwords do not match.");
    expect(validateChangePassword("current1", "newpassword1", "newpassword1")).toBeNull();
  });

  it("maps incorrect current password errors clearly", () => {
    expect(changePasswordErrorMessage("Invalid password", "fallback")).toBe("Current password is incorrect.");
    expect(changePasswordErrorMessage("Password is too short", "fallback")).toBe(
      "Password must be at least 8 characters.",
    );
    expect(changePasswordErrorMessage("Network error", "fallback")).toBe("Network error");
  });

  it("maps duplicate username errors clearly", () => {
    expect(authErrorMessage("Username is already taken. Please try another.", "x")).toContain("already taken");
    expect(authErrorMessage("Invalid username or password", "x")).toBe("Invalid username or password.");
  });
});
