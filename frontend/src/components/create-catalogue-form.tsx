"use client";

import { HomeIcon, MixIcon, ReaderIcon } from "@radix-ui/react-icons";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AreaDiscoveryForm } from "@/components/area-discovery-form";
import { CatalogueView } from "@/components/catalogue-view";
import { CatalogueTypeBadge } from "@/components/catalogue-type-badge";
import { StatusBadge } from "@/components/status-badge";
import { ProcessProgressBar } from "@/components/process-progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CatalogApiError, createCatalogue } from "@/lib/catalog-api";
import { validateCreateCatalogueForm, platformUrlHint, platformUrlMismatchMessage, urlMatchesPlatform, type CatalogFormErrors } from "@/lib/catalog-form";
import { saveCatalogue } from "@/lib/catalogue-store";
import type { CatalogueType, CatalogCreateResponse, Platform } from "@/lib/catalog-types";
import { extractionMessage, platformLabel } from "@/lib/catalog-types";
import { indeterminatePercent } from "@/lib/progress";
import { venueDisplayName, venueLocation } from "@/lib/restaurant-identity";
import { cn } from "@/lib/utils";

export function createProgressSteps(platform: Platform = "swiggy"): string[] {
  return [
    `Connecting to ${platformLabel(platform)}`,
    "Loading restaurant",
    "Extracting business information",
    "Extracting menu",
    "Extracting offers",
    "Extracting images",
    "Processing catalogue",
    "Saving catalogue",
  ];
}

export const CREATE_PROGRESS_STEPS = createProgressSteps("swiggy");

const TYPE_OPTIONS: Array<{ id: CatalogueType; title: string; hint: string; icon: typeof HomeIcon }> = [
  { id: "restaurant", title: "Restaurant", hint: "Menu, items, and FSSAI details", icon: HomeIcon },
  { id: "dineout", title: "Dineout", hint: "Venue, offers, menu pages, and photos", icon: ReaderIcon },
  { id: "both", title: "Both", hint: "Restaurant menu and Dineout venue, kept separate", icon: MixIcon },
];

export function CreateCatalogueForm({ organizationId }: { organizationId: string }) {
  const [mode, setMode] = useState<"single" | "area" | null>(null);
  const [catalogueType, setCatalogueType] = useState<CatalogueType | null>(null);
  const [platform, setPlatform] = useState<Platform>("swiggy");
  const [restaurantName, setRestaurantName] = useState("");
  const [fssai, setFssai] = useState("");
  const [swiggyUrl, setSwiggyUrl] = useState("");
  const [dineoutUrl, setDineoutUrl] = useState("");
  const [errors, setErrors] = useState<CatalogFormErrors>({});
  const [loading, setLoading] = useState(false);
  const [progressTick, setProgressTick] = useState(0);
  const [result, setResult] = useState<CatalogCreateResponse | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);
  const scrapeAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const nextPlatform = params.get("platform");
    const nextType = params.get("catalogue_type");
    if (nextPlatform === "swiggy" || nextPlatform === "zomato" || nextPlatform === "magicpin") {
      setPlatform(nextPlatform);
    }
    if (nextType === "restaurant" || nextType === "dineout" || nextType === "both") {
      setCatalogueType(nextType);
    }
  }, []);

  useEffect(() => {
    setResult(null);
  }, [organizationId]);

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

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!catalogueType) {
      return;
    }
    const values = {
      restaurant_name: restaurantName,
      fssai_number: fssai,
      swiggy_url: swiggyUrl,
      dineout_url: dineoutUrl,
      catalogue_type: catalogueType,
      platform,
    };
    const nextErrors = validateCreateCatalogueForm(values);
    setErrors(nextErrors);
    setRequestError(null);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }
    setLoading(true);
    setResult(null);
    setCancelled(false);
    scrapeAbortRef.current = new AbortController();
    try {
      const created = await createCatalogue(
        {
          restaurant_name: restaurantName,
          fssai_number: catalogueType === "dineout" ? fssai : fssai,
          swiggy_url: swiggyUrl,
          organization_id: organizationId,
          catalogue_type: catalogueType,
          platform,
          dineout_url: catalogueType === "both" ? dineoutUrl : undefined,
        },
        scrapeAbortRef.current.signal,
      );
      setResult(created);
      if (created.extraction_status === "ok") {
        saveCatalogue({
          id: created.id || crypto.randomUUID(),
          organizationId: created.organization_id || organizationId,
          createdAt: created.created_at || new Date().toISOString(),
          result: created,
        });
      }
    } catch (error) {
      setResult(null);
      if (error instanceof CatalogApiError && error.status === 499) {
        setCancelled(true);
        setRequestError(null);
        return;
      }
      setRequestError(
        error instanceof CatalogApiError
          ? error.message
          : "Something went wrong while creating the catalogue.",
      );
    } finally {
      setLoading(false);
      scrapeAbortRef.current = null;
    }
  }

  function cancelScraping() {
    scrapeAbortRef.current?.abort();
    setLoading(false);
    setCancelled(true);
    setRequestError(null);
  }

  function retry() {
    setResult(null);
    setRequestError(null);
    setCancelled(false);
  }

  if (!mode) {
    return <CreateModePicker onSelect={setMode} />;
  }
  if (mode === "area") {
    return <AreaDiscoveryForm organizationId={organizationId} onBack={() => setMode(null)} />;
  }

  if (!catalogueType) {
    return (
      <div className="max-w-2xl space-y-4">
        <h2 className="text-xl font-medium">What would you like to create?</h2>
        <div className="grid gap-3 phone:grid-cols-3">
          {TYPE_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setCatalogueType(option.id)}
              className="rounded-xl border border-border bg-card p-4 text-left hover:bg-accent"
            >
              <option.icon className="mb-3 size-5" />
              <p className="font-medium">{option.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{option.hint}</p>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const nameLabel = catalogueType === "dineout" ? "Venue Name" : "Restaurant Name";
  const label = platformLabel(platform);
  const urlLabel = `${label} URL`;
  const urlPlaceholder =
    platform === "zomato"
      ? "https://www.zomato.com/city/restaurant-name"
      : platform === "magicpin"
        ? "https://magicpin.in/City/Area/Restaurant/Name/store/..."
        : catalogueType === "dineout"
          ? "https://www.swiggy.com/restaurants/.../dineout"
          : "https://www.swiggy.com/city/...";

  const scrapeRunningLabel =
    catalogueType === "dineout"
      ? "Scraping dineout catalogue…"
      : catalogueType === "both"
        ? "Scraping restaurant and dineout catalogues…"
        : "Scraping restaurant catalogue…";

  return (
    <div className="space-y-8">
      <button type="button" className="text-sm text-muted-foreground hover:text-foreground" onClick={() => { setCatalogueType(null); setMode(null); }}>
        ← Change mode
      </button>
      <form className="max-w-xl space-y-4" onSubmit={(event) => void onSubmit(event)} noValidate>
        <div className="space-y-2">
          <p className="text-sm font-medium">Platform</p>
          <div className="grid gap-3 phone:grid-cols-3">
            {(["swiggy", "zomato", "magicpin"] as Platform[]).map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setPlatform(id);
                  if (swiggyUrl.trim() && !urlMatchesPlatform(id, swiggyUrl)) {
                    setErrors((current) => ({
                      ...current,
                      swiggy_url: platformUrlMismatchMessage(id),
                    }));
                  } else {
                    setErrors((current) => ({ ...current, swiggy_url: undefined }));
                  }
                }}
                className={cn(
                  "rounded-xl border border-border bg-card p-3 text-left hover:bg-accent",
                  platform === id && "bg-accent",
                )}
              >
                <p className="font-medium">{platformLabel(id)}</p>
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="restaurant_name">{nameLabel}</Label>
          <Input
            id="restaurant_name"
            value={restaurantName}
            onChange={(event) => setRestaurantName(event.target.value)}
          />
          {errors.restaurant_name ? <p className="text-sm text-destructive">{errors.restaurant_name}</p> : null}
        </div>
        {catalogueType !== "dineout" ? (
          <div className="space-y-2">
            <Label htmlFor="fssai_number">FSSAI License Number</Label>
            <Input id="fssai_number" value={fssai} onChange={(event) => setFssai(event.target.value)} />
            {errors.fssai_number ? <p className="text-sm text-destructive">{errors.fssai_number}</p> : null}
          </div>
        ) : null}
        <div className="space-y-2">
          <Label htmlFor="swiggy_url">{urlLabel}</Label>
          <Input
            id="swiggy_url"
            value={swiggyUrl}
            onChange={(event) => {
              const value = event.target.value;
              setSwiggyUrl(value);
              if (!value.trim()) {
                setErrors((current) => ({ ...current, swiggy_url: undefined }));
                return;
              }
              if (!urlMatchesPlatform(platform, value)) {
                setErrors((current) => ({
                  ...current,
                  swiggy_url: platformUrlMismatchMessage(platform),
                }));
              } else {
                setErrors((current) => ({ ...current, swiggy_url: undefined }));
              }
            }}
            placeholder={urlPlaceholder}
          />
          <p className="text-sm text-muted-foreground">{platformUrlHint(platform)}</p>
          {errors.swiggy_url ? <p className="text-sm text-destructive">{errors.swiggy_url}</p> : null}
        </div>
        {catalogueType === "both" ? (
          <div className="space-y-2">
            <Label htmlFor="dineout_url">{label} Dineout URL</Label>
            <Input
              id="dineout_url"
              value={dineoutUrl}
              onChange={(event) => setDineoutUrl(event.target.value)}
              placeholder={
                platform === "zomato"
                  ? "https://www.zomato.com/city/restaurant-name"
                  : platform === "magicpin"
                    ? "https://magicpin.in/City/Area/Restaurant/Name/store/..."
                    : "https://www.swiggy.com/restaurants/.../dineout"
              }
            />
            {errors.dineout_url ? <p className="text-sm text-destructive">{errors.dineout_url}</p> : null}
          </div>
        ) : null}
        <Button type="submit" disabled={loading} className={cn(loading && "opacity-80")}>
          {loading ? "Creating your catalogue..." : "Create Catalogue"}
        </Button>
      </form>
      {loading ? (
        <div className="space-y-3">
          <ProcessProgressBar
            phase="running"
            percent={indeterminatePercent(progressTick)}
            runningLabel={scrapeRunningLabel}
          />
          <Button type="button" variant="outline" onClick={cancelScraping}>
            Cancel scraping
          </Button>
        </div>
      ) : null}
      {cancelled ? (
        <p className="text-sm text-muted-foreground">Scraping cancelled.</p>
      ) : null}
      {requestError ? (
        <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-4">
          <p className="font-semibold text-destructive">Catalogue Scraping Failed</p>
          <p className="text-sm text-destructive">{requestError}</p>
          <Button type="button" variant="outline" size="sm" onClick={retry}>
            Retry
          </Button>
        </div>
      ) : null}
      {result ? (
        result.extraction_status === "ok" || result.extraction_status === "partial" ? (
          <div className="space-y-4">
            <ProcessProgressBar
              phase="completed"
              percent={100}
              completedLabel={result.extraction_status === "partial" ? "Catalogue partially created" : "Catalogue created"}
            />
            {result.extraction_status === "partial" ? (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-600 dark:text-amber-400">
                <p className="font-semibold">Catalogue Partially Scraped</p>
                <p>{result.error || "Some items or optional details could not be extracted, but usable catalogue data was harvested."}</p>
              </div>
            ) : null}
            <CatalogueCreatedSummary catalogue={result} />
          </div>
        ) : result.extraction_status === "blocked" ? (
          <CatalogueBlockedState onRetry={retry} platform={result.platform || platform} />
        ) : (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-4">
            <StatusBadge status={result.extraction_status} />
            <p className="font-semibold text-destructive">Catalogue Scraping Failed</p>
            <p className="text-sm text-destructive">{result.error || "Catalogue extraction failed."}</p>
            <Button type="button" variant="outline" size="sm" onClick={retry}>
              Retry
            </Button>
          </div>
        )
      ) : null}
    </div>
  );
}

export function CreateModePicker({ onSelect }: { onSelect: (mode: "single" | "area") => void }) {
  return (
    <div className="max-w-2xl space-y-4">
      <h2 className="text-xl font-medium">How would you like to create catalogues?</h2>
      <div className="grid gap-3 phone:grid-cols-2">
        <button type="button" onClick={() => onSelect("single")} className="rounded-xl border border-border bg-card p-4 text-left hover:bg-accent">
          <p className="font-medium">Single Venue</p>
          <p className="mt-1 text-sm text-muted-foreground">Paste one restaurant or Dineout URL.</p>
        </button>
        <button type="button" onClick={() => onSelect("area")} className="rounded-xl border border-border bg-card p-4 text-left hover:bg-accent">
          <p className="font-medium">Area / City</p>
          <p className="mt-1 text-sm text-muted-foreground">Discover and scrape available venues for any location.</p>
        </button>
      </div>
    </div>
  );
}

export function CatalogueTypePicker({ onSelect }: { onSelect: (type: CatalogueType) => void }) {
  return (
    <div className="max-w-2xl space-y-4">
      <h2 className="text-xl font-medium">What would you like to create?</h2>
      <div className="grid gap-3 phone:grid-cols-3">
        {TYPE_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onSelect(option.id)}
            className="rounded-xl border border-border bg-card p-4 text-left hover:bg-accent"
          >
            <option.icon className="mb-3 size-5" />
            <p className="font-medium">{option.title}</p>
            <p className="mt-1 text-sm text-muted-foreground">{option.hint}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

export function CatalogueCreateProgress({
  currentStep,
  steps = CREATE_PROGRESS_STEPS,
}: {
  currentStep: number;
  steps?: string[];
}) {
  const percent = Math.round(((currentStep + 1) / steps.length) * 100);
  return (
    <ProcessProgressBar
      phase="running"
      percent={percent}
      runningLabel="Creating your catalogue..."
    />
  );
}

export function CatalogueCreatedSummary({ catalogue }: { catalogue: CatalogCreateResponse }) {
  const name = venueDisplayName(catalogue);
  const location = venueLocation(catalogue);
  return (
    <div className="space-y-8">
      <div className="space-y-4 rounded-2xl border border-border bg-card p-6 text-card-foreground">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-medium">Catalogue Created</h2>
          <CatalogueTypeBadge type={catalogue.catalogue_type} />
        </div>
        <p className="text-lg">{name}</p>
        {location ? <p className="text-sm text-muted-foreground">{location}</p> : null}
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
          <span>Categories: {catalogue.categories?.length ?? 0}</span>
          <span>Items: {catalogue.item_count ?? 0}</span>
          <span>Images: {catalogue.image_count ?? 0}</span>
        </div>
        {catalogue.id ? (
          <Button asChild>
            <Link href={`/catalogues/${catalogue.id}`}>View Catalogue</Link>
          </Button>
        ) : null}
      </div>
      <CatalogueView catalogue={catalogue} />
    </div>
  );
}

export function CatalogueBlockedState({
  onRetry,
  platform = "swiggy",
}: {
  onRetry: () => void;
  platform?: Platform | string | null;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <h2 className="text-lg font-medium">{extractionMessage("blocked", null, platform)}</h2>
      <div className="flex gap-2">
        <Button type="button" onClick={onRetry}>
          Retry
        </Button>
        <Button asChild variant="outline">
          <Link href="/catalogues">Back</Link>
        </Button>
      </div>
    </div>
  );
}
