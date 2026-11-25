import { chartTitle } from "@/components/primitives";
import { cn } from "@/lib/utils";

export default function MetricCard({
  title,
  value,
  hint,
  className,
}: {
  title: string;
  value: string;
  hint?: string;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col", className)}>
      <h2 className={cn(chartTitle({ color: "mute", size: "sm" }), "mb-1")}>{title}</h2>
      <span className="text-xl font-medium">{value}</span>
      {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
    </section>
  );
}
