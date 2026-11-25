"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ProcessProgressBar } from "@/components/process-progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CatalogApiError, createAreaJob } from "@/lib/catalog-api";
import type { CatalogueType, Platform } from "@/lib/catalog-types";
import { platformLabel } from "@/lib/catalog-types";
import { indeterminatePercent } from "@/lib/progress";
import { cn } from "@/lib/utils";

const PLATFORMS: Platform[] = ["swiggy", "zomato", "magicpin"];
const TYPES: CatalogueType[] = ["restaurant", "dineout", "both"];

export function AreaDiscoveryForm({
  organizationId,
  onBack,
}: {
  organizationId: string;
  onBack?: () => void;
}) {
  const router = useRouter();
  const [location, setLocation] = useState("");
  const [platforms, setPlatforms] = useState<Platform[]>(["swiggy"]);
  const [catalogueType, setCatalogueType] = useState<CatalogueType>("restaurant");
  const [limitMode, setLimitMode] = useState<"all" | "custom">("all");
  const [customLimit, setCustomLimit] = useState("100");
  const [magicpinDining, setMagicpinDining] = useState<"all" | "budget" | "fine">("all");
  const [concurrency, setConcurrency] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progressTick, setProgressTick] = useState(0);
  const [cancelled, setCancelled] = useState(false);
  const scrapeAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!loading) {
      return;
    }
    setProgressTick(0);
    const timer = window.setInterval(() => {
      setProgressTick((current) => current + 1);
    }, 900);
    return () => window.clearInterval(timer);
  }, [loading]);

  function togglePlatform(id: Platform) {
    setPlatforms((current) => {
      if (current.includes(id)) {
        return current.filter((item) => item !== id);
      }
      return [...current, id];
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!location.trim()) {
      setError("Enter a city, locality, town or area.");
      return;
    }
    if (!platforms.length) {
      setError("Select at least one platform.");
      return;
    }
    const maxVenues = limitMode === "custom" ? Number(customLimit) : null;
    if (limitMode === "custom" && (!Number.isFinite(maxVenues) || (maxVenues || 0) < 1)) {
      setError("Enter a custom maximum of at least 1, or choose All available.");
      return;
    }
    setLoading(true);
    setCancelled(false);
    scrapeAbortRef.current = new AbortController();
    try {
      const job = await createAreaJob(
        {
          location: location.trim(),
          platforms,
          catalogue_type: catalogueType,
          organization_id: organizationId,
          max_venues: maxVenues,
          concurrency: Math.max(1, Number(concurrency) || 1),
          magicpin_dining: magicpinDining,
        },
        scrapeAbortRef.current.signal,
      );
      router.push(`/areas/${job.id}`);
    } catch (err) {
      if (err instanceof CatalogApiError && err.status === 499) {
        setCancelled(true);
        setError(null);
        return;
      }
      setError(err instanceof CatalogApiError ? err.message : "Discovery failed.");
    } finally {
      setLoading(false);
      scrapeAbortRef.current = null;
    }
  }

  function cancelDiscovery() {
    scrapeAbortRef.current?.abort();
    setLoading(false);
    setCancelled(true);
    setError(null);
  }

  return (
    <form className="max-w-xl space-y-4" onSubmit={(event) => void onSubmit(event)}>
      {onBack ? (
        <button type="button" className="text-sm text-muted-foreground hover:text-foreground" onClick={onBack}>
          ← Change mode
        </button>
      ) : null}
      <div className="space-y-2">
        <Label htmlFor="area-location">Location</Label>
        <Input
          id="area-location"
          value={location}
          onChange={(event) => setLocation(event.target.value)}
          placeholder="City, area or locality — typed into the location search, then the matching suggestion is selected"
        />
        <p className="text-xs text-muted-foreground">
          Same as the site: Swiggy homepage location box then Food Delivery or Dineout; Zomato header location; Magicpin Search Location then a category card.
        </p>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium">Platforms</p>
        <div className="flex flex-wrap gap-2">
          {PLATFORMS.map((id) => (
            <label key={id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <input type="checkbox" checked={platforms.includes(id)} onChange={() => togglePlatform(id)} />
              {platformLabel(id)}
            </label>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium">Catalogue type</p>
        <div className="grid gap-2 phone:grid-cols-3">
          {TYPES.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setCatalogueType(id)}
              className={cn("rounded-xl border border-border bg-card p-3 text-sm capitalize", catalogueType === id && "bg-accent")}
            >
              {id}
            </button>
          ))}
        </div>
      </div>
      {platforms.includes("magicpin") ? (
        <div className="space-y-2">
          <p className="text-sm font-medium">Magicpin dining</p>
          <div className="grid gap-2 phone:grid-cols-3">
            <button
              type="button"
              onClick={() => setMagicpinDining("all")}
              className={cn("rounded-xl border border-border bg-card p-3 text-left text-sm", magicpinDining === "all" && "bg-accent")}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setMagicpinDining("budget")}
              className={cn("rounded-xl border border-border bg-card p-3 text-left text-sm", magicpinDining === "budget" && "bg-accent")}
            >
              Budget Dining
            </button>
            <button
              type="button"
              onClick={() => setMagicpinDining("fine")}
              className={cn("rounded-xl border border-border bg-card p-3 text-left text-sm", magicpinDining === "fine" && "bg-accent")}
            >
              Fine Dining
            </button>
          </div>
          <p className="text-xs text-muted-foreground">Restaurant discovery uses Food Delivery. Dineout uses Budget Dining, Fine Dining, or both.</p>
        </div>
      ) : null}
      <div className="space-y-2">
        <Label htmlFor="max-venues">Maximum venues</Label>
        <select
          id="max-venues"
          className="flex h-10 w-full rounded-md border border-border bg-input px-3 text-sm"
          value={limitMode}
          onChange={(event) => setLimitMode(event.target.value as "all" | "custom")}
        >
          <option value="all">All available</option>
          <option value="custom">Custom limit</option>
        </select>
        {limitMode === "custom" ? (
          <Input value={customLimit} onChange={(event) => setCustomLimit(event.target.value)} inputMode="numeric" />
        ) : null}
      </div>
      <div className="space-y-2">
        <Label htmlFor="concurrency">Concurrent venue scrapes</Label>
        <Input id="concurrency" value={concurrency} onChange={(event) => setConcurrency(event.target.value)} inputMode="numeric" />
        <p className="text-xs text-muted-foreground">Start with 1. Increase only after the platform stays stable.</p>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {loading ? (
        <div className="space-y-3">
          <ProcessProgressBar
            phase="running"
            percent={indeterminatePercent(progressTick)}
            runningLabel="Discovering venues…"
          />
          <Button type="button" variant="outline" onClick={cancelDiscovery}>
            Cancel discovery
          </Button>
        </div>
      ) : null}
      {cancelled ? <p className="text-sm text-muted-foreground">Discovery cancelled.</p> : null}
      <Button type="submit" disabled={loading}>
        {loading ? "Discovering venues..." : "Discover venues"}
      </Button>
    </form>
  );
}
