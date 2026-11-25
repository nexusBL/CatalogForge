import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import ProfilePage from "@/app/(dashboard)/profile/page";
import SettingsPage from "@/app/(dashboard)/settings/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: () => undefined, push: () => undefined }),
}));

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    useSession: () => ({
      data: { user: { id: "user_1", name: "Bharath L", email: "owner@example.com" } },
      isPending: false,
    }),
    signOut: async () => undefined,
  },
}));

describe("profile and settings", () => {
  it("renders a profile card and personal/business editor sections", () => {
    const html = renderToStaticMarkup(<ProfilePage />);
    expect(html).toContain("Edit Profile");
    expect(html).toContain("Bharath L");
    expect(html).toContain("owner@example.com");
    expect(html).toContain("Account settings");
    expect(html).not.toContain("Personal");
  });

  it("renders change password fields on the profile page", () => {
    const html = renderToStaticMarkup(<ProfilePage />);
    expect(html).toContain("Change password");
    expect(html).toContain("Current password");
    expect(html).toContain("Confirm new password");
    expect(html).toContain("profile-current-password");
    expect(html).toContain("profile-new-password");
    expect(html).toContain("profile-confirm-password");
  });

  it("renders password, notifications, account settings, and logout", () => {
    const html = renderToStaticMarkup(<SettingsPage />);
    expect(html).toContain("Change password");
    expect(html).toContain("Notification preferences");
    expect(html).toContain("Account settings");
    expect(html).toContain("Logout");
    expect(html).toContain("Catalogue ready");
  });
});
