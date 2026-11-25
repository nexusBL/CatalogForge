import {
  GearIcon,
  HomeIcon,
  InfoCircledIcon,
  PlusIcon,
  ReaderIcon,
  StackIcon,
} from "@radix-ui/react-icons";
import type { ComponentType } from "react";

export type SiteConfig = typeof siteConfig;
export type NavIcon = ComponentType<{ className?: string }>;
export type NavItem = {
  icon: NavIcon;
  name: string;
  href: string;
};
export type NavSection = {
  label?: string;
  items: NavItem[];
};

export const siteConfig = {
  title: "CatalogForge",
  description: "Restaurant and Dineout catalogues.",
};

export const navSections: NavSection[] = [
  { items: [{ icon: HomeIcon, name: "Overview", href: "/overview" }] },
  {
    label: "RESTAURANT",
    items: [
      { icon: StackIcon, name: "My Restaurant", href: "/restaurant" },
      { icon: InfoCircledIcon, name: "About", href: "/restaurant/about" },
    ],
  },
  {
    label: "DINEOUT",
    items: [
      { icon: ReaderIcon, name: "My Dineout", href: "/dineout" },
      { icon: InfoCircledIcon, name: "About", href: "/dineout/about" },
    ],
  },
  {
    label: "CATALOGUE",
    items: [
      { icon: PlusIcon, name: "Create Catalogue", href: "/catalogues/new" },
      { icon: ReaderIcon, name: "Catalogues", href: "/catalogues" },
    ],
  },
  { items: [{ icon: GearIcon, name: "Settings", href: "/settings" }] },
];
