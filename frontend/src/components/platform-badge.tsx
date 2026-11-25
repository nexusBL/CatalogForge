import { platformLabel, type Platform } from "@/lib/catalog-types";

export function PlatformBadge({ platform }: { platform?: string | null }) {
  const label = platformLabel(platform as Platform | undefined);
  return (
    <span className="inline-flex rounded-full border border-border bg-card px-2 py-0.5 text-xs text-muted-foreground">
      {label}
    </span>
  );
}
