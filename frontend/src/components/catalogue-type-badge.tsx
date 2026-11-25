import { catalogueTypeLabel } from "@/lib/restaurant-identity";

export function CatalogueTypeBadge({ type }: { type?: string | null }) {
  return (
    <span className="inline-flex rounded-full border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      {catalogueTypeLabel(type)}
    </span>
  );
}
