import { cn } from "@/lib/utils";

export function LoadingSkeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} aria-hidden="true" />;
}

export function PageLoadingSkeleton() {
  return (
    <div className="space-y-4 p-6" role="status" aria-live="polite" aria-label="Loading">
      <LoadingSkeleton className="h-7 w-48" />
      <LoadingSkeleton className="h-4 w-full max-w-xl" />
      <LoadingSkeleton className="h-4 w-full max-w-lg" />
      <LoadingSkeleton className="h-32 w-full max-w-2xl" />
    </div>
  );
}
