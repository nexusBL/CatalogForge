import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const sessionState = {
  data: null as { user: { id: string; email: string } } | null,
  isPending: true,
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, refresh: () => undefined, replace: () => undefined }),
  usePathname: () => "/catalogues/new",
}));

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    useSession: () => sessionState,
    useListOrganizations: () => ({
      data: [{ id: "org_1", name: "Harbor Spice House" }],
      isPending: false,
    }),
  },
}));

describe("create catalogue session gate", () => {
  it("shows a loading state while the Better Auth session is still loading", async () => {
    sessionState.data = null;
    sessionState.isPending = true;
    const { default: CreateCataloguePage } = await import("@/app/(dashboard)/catalogues/new/page");
    const html = renderToStaticMarkup(<CreateCataloguePage />);
    expect(html).toContain('aria-label="Loading"');
    expect(html).not.toContain("You need to sign in before using catalogues.");
    expect(html).not.toContain("Swiggy Restaurant URL");
  });

  it("shows the sign-in message only after the session check has finished", async () => {
    sessionState.data = null;
    sessionState.isPending = false;
    const { default: CreateCataloguePage } = await import("@/app/(dashboard)/catalogues/new/page");
    const html = renderToStaticMarkup(<CreateCataloguePage />);
    expect(html).toContain("You need to sign in before using catalogues.");
  });
});
