import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import SideNav from "@/components/nav/side-nav";
import Navigation from "@/components/nav/side-nav/components/navigation";
import { TooltipProvider } from "@/components/ui/tooltip";
import { isNavActive } from "@/components/nav/side-nav/components/navigation";
import { profileInitials, profileLabel } from "@/components/nav/side-nav/components/profile-menu";
import { PlatformBadge } from "@/components/platform-badge";
import type { StoredCatalogue } from "@/lib/catalog-types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/catalogues/new",
  useRouter: () => ({ replace: () => undefined, push: () => undefined }),
}));

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    useSession: () => ({
      data: { user: { id: "user_1", email: "22bds013@iiitdwd.ac.in" } },
      isPending: false,
    }),
    useListOrganizations: () => ({
      data: [
        {
          id: "org_1",
          name: "https://www.swiggy.com/city/mangaluru/barbeque-nation-father-mullers-road-kankanady-rest302695",
        },
      ],
      isPending: false,
    }),
    signOut: async () => undefined,
  },
}));

const sampleCatalogues: StoredCatalogue[] = [
  {
    id: "cat_daffys_swiggy",
    organizationId: "org_1",
    createdAt: "2026-01-01T00:00:00Z",
    result: {
      extraction_status: "ok",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "1",
      source_url: "https://www.swiggy.com/city/bangalore/daffys-rest1",
      platform: "swiggy",
      catalogue_type: "restaurant",
      restaurant: { name: "Daffy's Brewgarden", outlet: "Indiranagar, Bangalore" },
    },
  },
  {
    id: "cat_daffys_zomato",
    organizationId: "org_1",
    createdAt: "2026-01-02T00:00:00Z",
    result: {
      extraction_status: "ok",
      restaurant_name: "Daffy's Brewgarden",
      fssai_number: "",
      source_url: "https://www.zomato.com/bangalore/daffys-brewgarden-indiranagar-bangalore",
      platform: "zomato",
      catalogue_type: "dineout",
      restaurant: { name: "Daffy's Brewgarden", outlet: "Indiranagar, Bangalore" },
    },
  },
];

describe("sidebar chrome", () => {
  it("renders CatalogForge navigation with profile at the bottom", () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <SideNav />
      </TooltipProvider>,
    );
    expect(html).toContain("CatalogForge");
    expect(html).toContain('aria-label="Collapse sidebar"');
    expect(html).not.toMatch(/aria-label="Collapse sidebar"[^>]*w-full/);
    expect(html).not.toMatch(/<aside[^>]*onClick/);
    expect(html).not.toMatch(/<span[^>]*>Collapse<\/span>/);
    expect(html).not.toContain("Swiggy catalogues");
    expect(html).toContain("City / Areas");
    expect(html).toContain("My Restaurant");
    expect(html).toContain("My Dineout");
    expect(html).toContain("Settings");
    expect(html).toContain("Baba AI");
    expect(html).toContain("Grading");
    expect(html).toContain("bg-sidebar");
    expect(html).toContain('data-collapsed="false"');
    expect(html.indexOf("Settings")).toBeLessThan(html.indexOf("Account menu"));
    expect(html).not.toContain("barbeque-nation");
    expect(html).not.toContain("https://www.swiggy.com");
  });

  it("expands Platforms, Restaurant, and Dineout by default", () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Navigation />
      </TooltipProvider>,
    );
    expect(html).toContain("Platforms");
    expect(html).toContain("Swiggy");
    expect(html).toContain("Zomato");
    expect(html).toContain("Magicpin");
    expect(html).toContain("Restaurant");
    expect(html).toContain("Dineout");
    expect(html).toContain("Both");
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain("pl-3");
  });

  it("lists created catalogues under restaurant and dineout with platform identity", () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Navigation catalogues={sampleCatalogues} />
      </TooltipProvider>,
    );
    expect(html).toContain("Brewgarden");
    expect(html).toContain("Indiranagar, Bangalore · Swiggy · Restaurant");
    expect(html).toContain("Indiranagar, Bangalore · Zomato · Dineout");
    expect(html).toContain("/catalogues/cat_daffys_swiggy");
    expect(html).toContain("/catalogues/cat_daffys_swiggy/improvements");
    expect(html).toContain("/catalogues/cat_daffys_swiggy/media");
    expect(html).toContain("/catalogues/cat_daffys_zomato");
    expect(html).toContain("AI Improvements");
    expect(html).toContain("Generated Media");
  });

  it("shows icons and tooltips when the sidebar is collapsed", () => {
    const html = renderToStaticMarkup(
      <TooltipProvider>
        <Navigation collapsed catalogues={sampleCatalogues} />
      </TooltipProvider>,
    );
    expect(html).toContain("sr-only");
    expect(html).toContain("Overview");
    expect(html).not.toContain("uppercase tracking-wide");
  });

  it("keeps grayscale tokens in light and dark wrappers", () => {
    const html = renderToStaticMarkup(
      <div className="dark bg-sidebar text-foreground">
        <TooltipProvider>
          <Navigation />
        </TooltipProvider>
      </div>,
    );
    expect(html).toContain("dark");
    expect(html).toContain("bg-sidebar");
    expect(html).toContain("text-foreground");
    expect(html).toContain("hover:bg-selected");
    expect(html).not.toContain("bg-blue");
    expect(html).not.toContain("navy");
  });

  it("renders a subtle platform badge", () => {
    const html = renderToStaticMarkup(<PlatformBadge platform="magicpin" />);
    expect(html).toContain("Magicpin");
    expect(html).toContain("text-muted-foreground");
    expect(html).toContain("border-border");
  });

  it("marks create catalogue as active and keeps catalogue list inactive", () => {
    expect(isNavActive("/catalogues/new", "/catalogues/new")).toBe(true);
    expect(isNavActive("/catalogues", "/catalogues/new")).toBe(false);
    expect(isNavActive("/catalogues", "/catalogues/abc")).toBe(true);
    expect(isNavActive("/catalogues/abc", "/catalogues/abc/improvements")).toBe(true);
    expect(isNavActive("/catalogues/abc", "/catalogues/abc/media")).toBe(true);
    expect(isNavActive("/catalogues/new?platform=zomato", "/catalogues/new")).toBe(true);
    expect(isNavActive("/baba-ai", "/baba-ai")).toBe(true);
    expect(isNavActive("/baba-ai?catalogue=cat_1", "/baba-ai")).toBe(true);
    expect(isNavActive("/baba-ai", "/catalogues/cat_1")).toBe(false);
    expect(isNavActive("/grading", "/grading")).toBe(true);
    expect(isNavActive("/grading", "/grading/cat_1")).toBe(true);
    expect(isNavActive("/grading", "/catalogues/cat_1")).toBe(false);
  });

  it("uses authenticated profile details without fabricating a name", () => {
    expect(profileLabel({ email: "owner@example.com" })).toBe("owner@example.com");
    expect(profileInitials("Harbor Spice")).toBe("HS");
  });
});
