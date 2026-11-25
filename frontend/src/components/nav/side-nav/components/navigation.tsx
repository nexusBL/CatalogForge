"use client";

import {
  ChevronDownIcon,
  ChevronRightIcon,
  GearIcon,
  HomeIcon,
  InfoCircledIcon,
  MixIcon,
  PlusIcon,
  ReaderIcon,
  StackIcon,
  StarIcon,
} from "@radix-ui/react-icons";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { authClient } from "@/lib/auth-client";
import { listCataloguesApi } from "@/lib/catalog-api";
import { CATALOGUES_CHANGED_EVENT, listCatalogues } from "@/lib/catalogue-store";
import type { Platform, StoredCatalogue } from "@/lib/catalog-types";
import { platformLabel } from "@/lib/catalog-types";
import { babaAiHref, catalogueIdFromPathname } from "@/lib/assistant-ui";
import { catalogueManageHref } from "@/lib/manage-catalogue-ui";
import {
  CATALOGUE_TYPES,
  PLATFORMS,
  cataloguesForDomain,
  cataloguesHref,
  createCatalogueHref,
  navCatalogueItem,
} from "@/lib/nav-catalogues";
import { cn } from "@/lib/utils";

const EXPANDED_KEY = "hecto-baba-nav-expanded";
const DEFAULT_EXPANDED = {
  platforms: true,
  restaurant: true,
  dineout: true,
  catalogue: true,
};

export function isNavActive(href: string, pathname: string): boolean {
  const path = href.split("?")[0];
  if (path === "/baba-ai") {
    return pathname === "/baba-ai";
  }
  if (path === "/grading") {
    return pathname === "/grading" || pathname.startsWith("/grading/");
  }
  if (path === "/catalogues") {
    return pathname === "/catalogues" || /^\/catalogues\/(?!new(?:\/|$)).+/.test(pathname);
  }
  if (path === "/catalogues/new") {
    return pathname === "/catalogues/new";
  }
  if (/^\/catalogues\/[^/]+$/.test(path)) {
    return pathname === path || pathname.startsWith(`${path}/`);
  }
  return pathname === path;
}

function readExpanded(): typeof DEFAULT_EXPANDED {
  if (typeof window === "undefined") {
    return DEFAULT_EXPANDED;
  }
  try {
    const stored = window.localStorage.getItem(EXPANDED_KEY);
    if (!stored) {
      return DEFAULT_EXPANDED;
    }
    return { ...DEFAULT_EXPANDED, ...JSON.parse(stored) };
  } catch {
    return DEFAULT_EXPANDED;
  }
}

export default function Navigation({
  collapsed = false,
  catalogues: cataloguesProp,
}: {
  collapsed?: boolean;
  catalogues?: StoredCatalogue[];
}) {
  const pathname = usePathname();
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [catalogues, setCatalogues] = useState<StoredCatalogue[]>(cataloguesProp || []);
  const [expanded, setExpanded] = useState(DEFAULT_EXPANDED);

  useEffect(() => {
    setExpanded(readExpanded());
  }, []);

  function loadCatalogues(orgId: string) {
    setCatalogues(listCatalogues(orgId));
    listCataloguesApi(orgId)
      .then((rows) => {
        setCatalogues(rows);
      })
      .catch(() => {
        setCatalogues(listCatalogues(orgId));
      });
  }

  useEffect(() => {
    if (cataloguesProp) {
      setCatalogues(cataloguesProp);
      return;
    }
    if (!organizationId) {
      setCatalogues([]);
      return;
    }
    let cancelled = false;
    loadCatalogues(organizationId);
    function onCataloguesChanged(event: Event) {
      const detail = (event as CustomEvent<{ organizationId: string }>).detail;
      if (!cancelled && detail?.organizationId === organizationId) {
        loadCatalogues(organizationId);
      }
    }
    window.addEventListener(CATALOGUES_CHANGED_EVENT, onCataloguesChanged);
    return () => {
      cancelled = true;
      window.removeEventListener(CATALOGUES_CHANGED_EVENT, onCataloguesChanged);
    };
  }, [organizationId, cataloguesProp]);

  function toggle(key: keyof typeof DEFAULT_EXPANDED) {
    setExpanded((current) => {
      const next = { ...current, [key]: !current[key] };
      window.localStorage.setItem(EXPANDED_KEY, JSON.stringify(next));
      return next;
    });
  }

  const restaurantItems = cataloguesForDomain(catalogues, "restaurant").map(navCatalogueItem);
  const dineoutItems = cataloguesForDomain(catalogues, "dineout").map(navCatalogueItem);

  return (
    <nav className="flex flex-grow flex-col gap-y-3 overflow-y-auto p-2" aria-label="Primary">
      <NavLink href="/overview" icon={HomeIcon} label="Overview" pathname={pathname} collapsed={collapsed} />
      <NavLink href="/areas" icon={StackIcon} label="City / Areas" pathname={pathname} collapsed={collapsed} />

      <Expandable
        label="Platforms"
        icon={MixIcon}
        open={expanded.platforms}
        collapsed={collapsed}
        pathname={pathname}
        onToggle={() => toggle("platforms")}
        fallbackHref={createCatalogueHref()}
      >
        {PLATFORMS.map((platform) => (
          <PlatformBranch key={platform} platform={platform} pathname={pathname} collapsed={collapsed} />
        ))}
      </Expandable>

      <Expandable
        label="Restaurant"
        icon={StackIcon}
        open={expanded.restaurant}
        collapsed={collapsed}
        pathname={pathname}
        onToggle={() => toggle("restaurant")}
        fallbackHref="/restaurant"
      >
        <NavLink href="/restaurant" icon={StackIcon} label="My Restaurant" pathname={pathname} collapsed={collapsed} nested />
        <NavLink href="/restaurant/about" icon={InfoCircledIcon} label="About" pathname={pathname} collapsed={collapsed} nested />
        <NavLink
          href={createCatalogueHref(undefined, "restaurant")}
          icon={PlusIcon}
          label="Create Catalogue"
          pathname={pathname}
          collapsed={collapsed}
          nested
        />
        <NavLink
          href={cataloguesHref({ type: "restaurant" })}
          icon={ReaderIcon}
          label="Catalogues"
          pathname={pathname}
          collapsed={collapsed}
          nested
        />
        {restaurantItems.map((item) => (
          <CatalogueChild key={`restaurant-${item.id}`} item={item} pathname={pathname} collapsed={collapsed} />
        ))}
      </Expandable>

      <Expandable
        label="Dineout"
        icon={ReaderIcon}
        open={expanded.dineout}
        collapsed={collapsed}
        pathname={pathname}
        onToggle={() => toggle("dineout")}
        fallbackHref="/dineout"
      >
        <NavLink href="/dineout" icon={ReaderIcon} label="My Dineout" pathname={pathname} collapsed={collapsed} nested />
        <NavLink href="/dineout/about" icon={InfoCircledIcon} label="About" pathname={pathname} collapsed={collapsed} nested />
        <NavLink
          href={createCatalogueHref(undefined, "dineout")}
          icon={PlusIcon}
          label="Create Catalogue"
          pathname={pathname}
          collapsed={collapsed}
          nested
        />
        <NavLink
          href={cataloguesHref({ type: "dineout" })}
          icon={ReaderIcon}
          label="Catalogues"
          pathname={pathname}
          collapsed={collapsed}
          nested
        />
        {dineoutItems.map((item) => (
          <CatalogueChild key={`dineout-${item.id}`} item={item} pathname={pathname} collapsed={collapsed} />
        ))}
      </Expandable>

      <Expandable
        label="Catalogue"
        icon={PlusIcon}
        open={expanded.catalogue}
        collapsed={collapsed}
        pathname={pathname}
        onToggle={() => toggle("catalogue")}
        fallbackHref="/catalogues"
      >
        <NavLink href={createCatalogueHref()} icon={PlusIcon} label="Create Catalogue" pathname={pathname} collapsed={collapsed} nested />
        <NavLink href="/catalogues" icon={ReaderIcon} label="Catalogues" pathname={pathname} collapsed={collapsed} nested />
      </Expandable>

      <NavLink href="/grading" icon={StarIcon} label="Grading" pathname={pathname} collapsed={collapsed} />

      <NavLink
        href={pathname === "/baba-ai" || pathname.startsWith("/baba-ai?") ? "/baba-ai" : babaAiHref(catalogueIdFromPathname(pathname))}
        icon={BabaSparkIcon}
        label="Baba AI"
        pathname={pathname}
        collapsed={collapsed}
      />

      <NavLink href="/settings" icon={GearIcon} label="Settings" pathname={pathname} collapsed={collapsed} />
    </nav>
  );
}

function PlatformBranch({
  platform,
  pathname,
  collapsed,
}: {
  platform: Platform;
  pathname: string;
  collapsed: boolean;
}) {
  const storageKey = `platform-${platform}`;
  const [open, setOpen] = useState(true);
  useEffect(() => {
    const stored = window.localStorage.getItem(`${EXPANDED_KEY}-${storageKey}`);
    if (stored === "0") {
      setOpen(false);
    }
  }, [storageKey]);

  function toggle() {
    setOpen((current) => {
      const next = !current;
      window.localStorage.setItem(`${EXPANDED_KEY}-${storageKey}`, next ? "1" : "0");
      return next;
    });
  }

  const label = platformLabel(platform);
  if (collapsed) {
    return (
      <NavLink href={createCatalogueHref(platform)} icon={MixIcon} label={label} pathname={pathname} collapsed />
    );
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-foreground hover:bg-selected"
      >
        {open ? <ChevronDownIcon className="h-3.5 w-3.5 shrink-0" /> : <ChevronRightIcon className="h-3.5 w-3.5 shrink-0" />}
        <span>{label}</span>
      </button>
      {open
        ? CATALOGUE_TYPES.map((type) => (
            <NavLink
              key={`${platform}-${type}`}
              href={createCatalogueHref(platform, type)}
              icon={type === "dineout" ? ReaderIcon : type === "both" ? MixIcon : StackIcon}
              label={type === "both" ? "Both" : type === "dineout" ? "Dineout" : "Restaurant"}
              pathname={pathname}
              collapsed={false}
              nested
            />
          ))
        : null}
    </div>
  );
}

function Expandable({
  label,
  icon: Icon,
  open,
  collapsed,
  pathname,
  onToggle,
  fallbackHref,
  children,
}: {
  label: string;
  icon: typeof HomeIcon;
  open: boolean;
  collapsed: boolean;
  pathname: string;
  onToggle: () => void;
  fallbackHref: string;
  children: ReactNode;
}) {
  if (collapsed) {
    return <NavLink href={fallbackHref} icon={Icon} label={label} pathname={pathname} collapsed />;
  }
  return (
    <div className="space-y-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-foreground hover:bg-selected"
      >
        <Icon className="h-4 w-4 shrink-0" />
        <span className="flex-1 text-sm font-medium uppercase tracking-wide">{label}</span>
        {open ? <ChevronDownIcon className="h-4 w-4 shrink-0" /> : <ChevronRightIcon className="h-4 w-4 shrink-0" />}
      </button>
      {open ? <div className="space-y-1 pl-3">{children}</div> : null}
    </div>
  );
}

function CatalogueChild({
  item,
  pathname,
  collapsed,
}: {
  item: ReturnType<typeof navCatalogueItem>;
  pathname: string;
  collapsed: boolean;
}) {
  const active = isNavActive(item.href, pathname);
  const improvementsHref = `${item.href}/improvements`;
  const mediaHref = `${item.href}/media`;
  const manageHref = catalogueManageHref(item.id);
  const improvementsActive = pathname === improvementsHref || pathname.startsWith(`${improvementsHref}?`);
  const mediaActive = pathname === mediaHref || pathname.startsWith(`${mediaHref}?`);
  const manageActive = pathname === manageHref || pathname.startsWith(`${manageHref}?`);
  const link = (
    <Link
      href={item.href}
      aria-current={active && !improvementsActive && !mediaActive && !manageActive ? "page" : undefined}
      className={cn(
        "flex flex-col rounded-md px-2 py-1.5 text-foreground transition-colors duration-150 hover:bg-selected",
        collapsed ? "items-center" : "gap-0.5",
        active ? "bg-selected" : "bg-transparent",
      )}
    >
      <span className={cn("truncate text-sm", collapsed && "sr-only")}>{item.name}</span>
      {collapsed ? null : <span className="truncate text-[11px] text-muted-foreground">{item.subtitle}</span>}
    </Link>
  );
  if (collapsed) {
    return (
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right">{item.identity}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <div className="space-y-1">
      {link}
      <Link
        href={improvementsHref}
        aria-current={improvementsActive ? "page" : undefined}
        className={cn(
          "block rounded-md px-2 py-1 pl-4 text-xs text-muted-foreground transition-colors duration-150 hover:bg-selected hover:text-foreground",
          improvementsActive ? "bg-selected text-foreground" : "bg-transparent",
        )}
      >
        Grade / AI Improvements
      </Link>
      <Link
        href={manageHref}
        aria-current={manageActive ? "page" : undefined}
        className={cn(
          "block rounded-md px-2 py-1 pl-4 text-xs text-muted-foreground transition-colors duration-150 hover:bg-selected hover:text-foreground",
          manageActive ? "bg-selected text-foreground" : "bg-transparent",
        )}
      >
        Manage Catalogue
      </Link>
      <Link
        href={mediaHref}
        aria-current={mediaActive ? "page" : undefined}
        className={cn(
          "block rounded-md px-2 py-1 pl-4 text-xs text-muted-foreground transition-colors duration-150 hover:bg-selected hover:text-foreground",
          mediaActive ? "bg-selected text-foreground" : "bg-transparent",
        )}
      >
        Generated Media
      </Link>
    </div>
  );
}

function BabaSparkIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden className={className}>
      <path d="M8 1.1c.18 2.15.96 2.93 3.1 3.1C8.96 5.37 8.18 6.15 8 8.3 7.82 6.15 7.04 5.37 4.9 4.2 7.04 4.03 7.82 3.25 8 1.1zm-4.2 6.7c.12 1.35.6 1.83 1.95 1.95-1.35.12-1.83.6-1.95 1.95-.12-1.35-.6-1.83-1.95-1.95 1.35-.12 1.83-.6 1.95-1.95zm8.55.85c.1 1.05.47 1.42 1.52 1.52-1.05.1-1.42.47-1.52 1.52-.1-1.05-.47-1.42-1.52-1.52 1.05-.1 1.42-.47 1.52-1.52z" />
    </svg>
  );
}

function NavLink({
  href,
  icon: Icon,
  label,
  pathname,
  collapsed,
  nested = false,
}: {
  href: string;
  icon: ComponentType<{ className?: string }>;
  label: string;
  pathname: string;
  collapsed: boolean;
  nested?: boolean;
}) {
  const active = isNavActive(href, pathname);
  const link = (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center rounded-md px-2 py-1.5 text-foreground transition-colors duration-150 hover:bg-selected",
        collapsed ? "justify-center" : "gap-2",
        nested && !collapsed && "text-sm",
        active ? "bg-selected" : "bg-transparent",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {collapsed ? <span className="sr-only">{label}</span> : <span className="text-sm">{label}</span>}
    </Link>
  );
  if (!collapsed) {
    return link;
  }
  return (
    <Tooltip delayDuration={200}>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}
