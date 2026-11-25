import { Suspense } from "react";
import { BabaAiPage } from "@/components/baba-ai-page";
import { DashboardShell } from "@/components/dashboard-shell";

export default function BabaAiRoutePage() {
  return (
    <Suspense
      fallback={
        <DashboardShell title="Baba AI">
          <p className="px-6 py-10 text-sm text-muted-foreground">Loading Baba AI…</p>
        </DashboardShell>
      }
    >
      <BabaAiPage />
    </Suspense>
  );
}
