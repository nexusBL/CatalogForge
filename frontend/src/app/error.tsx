"use client";

import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

const AUTO_RETRY_KEY = "catalogforge:error-auto-retried";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const retriedRef = useRef(false);

  useEffect(() => {
    console.error(error);
  }, [error]);

  useEffect(() => {
    if (retriedRef.current || typeof window === "undefined") {
      return;
    }
    if (window.sessionStorage.getItem(AUTO_RETRY_KEY) === "1") {
      return;
    }
    retriedRef.current = true;
    const timer = window.setTimeout(() => {
      window.sessionStorage.setItem(AUTO_RETRY_KEY, "1");
      reset();
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [reset]);

  function tryAgain() {
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(AUTO_RETRY_KEY);
    }
    reset();
  }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-4">
      <div className="w-full max-w-md space-y-4 rounded-lg border border-border bg-card p-8 text-center shadow-sm">
        <h1 className="text-xl font-medium">Something went wrong</h1>
        <p className="text-sm text-muted-foreground">
          The page failed to load. Retrying in 5 seconds if your connection is back.
        </p>
        <Button type="button" onClick={tryAgain}>
          Try again now
        </Button>
      </div>
    </div>
  );
}