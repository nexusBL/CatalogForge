"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { authClient } from "@/lib/auth-client";
import { isAuthenticatedSession } from "@/lib/auth-guard";
import { PageLoadingSkeleton } from "@/components/loading-skeleton";

export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data: session, isPending } = authClient.useSession();

  useEffect(() => {
    if (!isPending && !isAuthenticatedSession(session)) {
      router.replace("/");
    }
  }, [isPending, session, router]);

  if (isPending) {
    return <PageLoadingSkeleton />;
  }
  if (!isAuthenticatedSession(session)) {
    return <p className="p-6 text-sm text-muted-foreground">Redirecting to sign in…</p>;
  }
  return <>{children}</>;
}
