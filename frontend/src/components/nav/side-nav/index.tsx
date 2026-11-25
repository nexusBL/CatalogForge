"use client";

import { DoubleArrowLeftIcon, DoubleArrowRightIcon } from "@radix-ui/react-icons";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import Brand from "./components/brand";
import Navigation from "./components/navigation";
import { ProfileMenu } from "./components/profile-menu";

const STORAGE_KEY = "hecto-baba-sidebar-collapsed";

export default function SideNav() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "1") {
      setCollapsed(true);
    }
  }, []);

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

  return (
    <>
      <button
        className={cn(
          "fixed left-0 top-12 z-50 rounded-r-md border border-border bg-secondary px-2 py-1.5 text-foreground shadow-md hover:bg-accent tablet:hidden",
          "transition-transform duration-150 ease-in-out",
          mobileOpen ? "translate-x-60" : "translate-x-0",
        )}
        aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
        onClick={() => setMobileOpen(!mobileOpen)}
      >
        {mobileOpen ? <DoubleArrowLeftIcon /> : <DoubleArrowRightIcon />}
      </button>
      <aside
        data-collapsed={collapsed ? "true" : "false"}
        className={cn(
          "fixed bottom-0 left-0 top-0 z-40 flex h-[100dvh] shrink-0 flex-col border-r border-border bg-sidebar text-foreground tablet:sticky tablet:translate-x-0",
          "transition-[width,transform] duration-150 ease-in-out",
          collapsed ? "w-14" : "w-60",
          mobileOpen ? "translate-x-0" : "-translate-x-full tablet:translate-x-0",
        )}
      >
        <Brand collapsed={collapsed} onToggle={toggleCollapsed} />
        <Navigation collapsed={collapsed} />
        <div className="mt-auto border-t border-border p-2">
          <ProfileMenu collapsed={collapsed} />
        </div>
      </aside>
    </>
  );
}
