import { cn } from "@/lib/utils";

export default function Brand({
  collapsed = false,
  onToggle,
}: {
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  return (
    <div className="relative my-2 flex items-center justify-center px-3 py-4">
      <div className="dot-matrix pointer-events-none absolute left-0 top-0 -z-10 h-full w-full" />
      <button
        type="button"
        onClick={onToggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className={cn(
          "relative z-10 rounded-md px-1.5 py-0.5 text-foreground hover:bg-selected",
          collapsed ? "text-xs" : "text-sm",
        )}
      >
        <span className="font-medium">{collapsed ? "CF" : "CatalogForge"}</span>
      </button>
    </div>
  );
}
