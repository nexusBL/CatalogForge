import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { LoginForm } from "@/components/login-form";
import { SignupForm } from "@/components/signup-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, refresh: () => undefined }),
}));

describe("auth forms", () => {
  it("shows username and password login first", () => {
    const html = renderToStaticMarkup(<LoginForm />);
    expect(html).toContain("Username");
    expect(html).toContain("Password");
    expect(html).toContain("Sign In");
    expect(html).toContain("Forgot password?");
    expect(html).toContain("Sign in with Email OTP");
    expect(html).toContain("Create Account");
    expect(html).not.toContain("Send OTP");
  });

  it("keeps the email OTP login available", () => {
    const html = renderToStaticMarkup(<LoginForm initialMode="otp" />);
    expect(html).toContain("Email");
    expect(html).toContain("Send OTP");
    expect(html).toContain("Back to username login");
  });

  it("renders required signup fields including username", () => {
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain("Create Account");
    expect(html).toContain("Name");
    expect(html).toContain("Email");
    expect(html).toContain("Username");
    expect(html).toContain("Confirm Password");
    expect(html).toContain("Sign In");
  });
});
