"use client";

import { Provider as JotaiProvider } from "jotai";
import { ModeThemeProvider } from "@/components/providers/mode-theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <JotaiProvider>
      <ModeThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      </ModeThemeProvider>
    </JotaiProvider>
  );
}
