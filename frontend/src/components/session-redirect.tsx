"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { authClient } from "@/lib/auth-client";
import { isAuthenticatedSession } from "@/lib/auth-guard";

export function SessionRedirect() {
  const router = useRouter();
  const { data: session, isPending } = authClient.useSession();

  useEffect(() => {
    if (!isPending && isAuthenticatedSession(session)) {
      router.replace("/overview");
    }
  }, [isPending, session, router]);

  return null;
}
