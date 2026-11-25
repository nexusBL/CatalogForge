"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PlatformBadge } from "@/components/platform-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DeleteDiscoveryJobButton } from "@/components/delete-discovery-job-button";
import {
  cancelAreaJobApi,
  CatalogApiError,
  scrapeAreaBatchApi,
  startAreaJobApi,
} from "@/lib/catalog-api";
import { ProcessProgressBar } from "@/components/process-progress";
import {
  canDeleteDiscoveryJob,
  discoveryPercent,
  filterVenues,
  jobLocation,
  locationMatchLabel,
  pageSlice,
  type AreaJob,
} from "@/lib/area-jobs";
import { scrapePercent, scrapePhase } from "@/lib/progress";
import { claimScrapeTick, releaseScrapeTick } from "@/lib/area-scrape-poll";
import { platformLabel } from "@/lib/catalog-types";
import { isDistanceText } from "@/lib/restaurant-identity";
import { cn } from "@/lib/utils";

export function AreaJobView({
  job: initial,
  organizationId,
}: {
  job: AreaJob;
  organizationId: string;
}) {
  const [job, setJob] = useState(initial);
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState("all");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [locationMatch, setLocationMatch] = useState("all");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Record<string, boolean>>(() =>
    Object.fromEntries((initial.venues || []).map((item) => [item.identity_key || item.venue_url, item.selected !== false])),
  );
  const [actions, setActions] = useState<Record<string, "skip" | "rescrape" | "update">>(() =>
    Object.fromEntries(
      (initial.venues || [])
        .filter((item) => item.existing_catalogue_id)
        .map((item) => [item.identity_key || item.venue_url, item.existing_action || "skip"]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  const filtered = useMemo(
    () => filterVenues(job.venues || [], { search, platform, type, status, location_match: locationMatch }),
    [job.venues, search, platform, type, status, locationMatch],
  );
  const rows = pageSlice(filtered, page);
  const pages = Math.max(1, Math.ceil(filtered.length / 50));
  const review = job.status === "awaiting_confirmation";
  const scraping = job.status === "scraping" || job.status === "queued" || busy;
  const scrapeDone = job.status === "completed" || job.status === "partially_completed";
  const scrapeBarPhase = scraping ? "running" : scrapeDone ? "completed" : scrapePhase(job);
  const discoveryDone =
    job.status === "awaiting_confirmation" ||
    job.status === "queued" ||
    job.status === "scraping" ||
    scrapeDone ||
    job.status === "failed";
  const discovered = job.discovered_count ?? job.venues.length;

  useEffect(() => {
    if (!scraping) {
      return;
    }
    let cancelled = false;
    const inFlight = { current: false };
    async function tick() {
      if (!claimScrapeTick(inFlight)) {
        return;
      }
      try {
        const next = await scrapeAreaBatchApi(job.id, organizationId);
        if (!cancelled) {
          setJob(next);
          setScrapeError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setBusy(false);
          setScrapeError(
            error instanceof CatalogApiError
              ? error.message
              : "Scraping paused. Check your connection and reload the page.",
          );
        }
      } finally {
        releaseScrapeTick(inFlight);
      }
    }
    const timer = window.setInterval(() => void tick(), 1200);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [scraping, job.id, organizationId]);

  async function start() {
    setBusy(true);
    try {
      const keys = Object.entries(selected)
        .filter(([, on]) => on)
        .map(([key]) => key);
      const next = await startAreaJobApi(job.id, {
        organization_id: organizationId,
        selected_keys: keys,
        existing_actions: actions,
      });
      setJob(next);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      setJob(await cancelAreaJobApi(job.id, organizationId));
    } finally {
      setBusy(false);
    }
  }

  function selectAll(value: boolean) {
    setSelected(Object.fromEntries((job.venues || []).map((item) => [item.identity_key || item.venue_url, value])));
  }

  return (
    <div className="space-y-6">
      <section className="space-y-2 rounded-xl border border-border bg-card p-5">
        <p className="text-sm text-muted-foreground">Location</p>
        <p className="text-xl font-medium">{jobLocation(job) || "Area job"}</p>
        {job.location?.city || job.location?.state ? (
          <p className="text-sm text-muted-foreground">
            {[job.location?.locality, job.location?.city, job.location?.state, job.location?.country].filter(Boolean).join(", ")}
            {job.location?.latitude != null && job.location?.longitude != null
              ? ` · ${Number(job.location.latitude).toFixed(4)}, ${Number(job.location.longitude).toFixed(4)}`
              : ""}
          </p>
        ) : null}
        <p className="text-sm text-muted-foreground">
          {job.platforms.map((item) => platformLabel(item)).join(", ")} · {job.catalogue_type}
        </p>
        <p className="text-sm capitalize">Status: {job.status === "failed" ? "Failed" : job.status.replaceAll("_", " ")}</p>
        {job.error ? <p className="text-sm text-destructive">{job.error}</p> : null}
        <p className="text-sm">Discovered: {discovered} venues</p>
        {job.discovery_scope === "delivery_to_location" ? (
          <div className="space-y-1 text-sm">
            <p>Swiggy restaurant results are a delivery feed for this pin, not a directory of outlets in this area.</p>
            <p>Located here: {job.located_here_count ?? 0}</p>
            <p>Delivers here: {job.delivers_here_count ?? 0}</p>
            <p>Location unknown: {job.unknown_location_count ?? 0}</p>
          </div>
        ) : null}
        <div className="space-y-2">
          {job.status === "discovering" ? (
            <ProcessProgressBar
              phase="running"
              percent={discoveryPercent(job)}
              runningLabel="Discovering venues…"
            />
          ) : discoveryDone ? (
            <ProcessProgressBar phase="completed" percent={100} completedLabel="Discovery completed" />
          ) : null}
        </div>
        {scrapeBarPhase !== "idle" && scrapeBarPhase !== "failed" ? (
          <ProcessProgressBar
            phase={scrapeBarPhase === "running" ? "running" : "completed"}
            percent={scraping ? scrapePercent(job) : 100}
            runningLabel="Scraping catalogues…"
            completedLabel="Scraping completed"
          />
        ) : null}
        {job.status === "failed" ? (
          <ProcessProgressBar phase="failed" percent={scrapePercent(job)} failedLabel="Scraping failed" />
        ) : null}
        {scrapeError ? <p className="text-sm text-destructive">{scrapeError}</p> : null}
      </section>

      <div className="flex flex-wrap gap-2">
        <Input className="max-w-xs" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search venue or location" />
        <select className="h-10 rounded-md border border-border bg-input px-2 text-sm" value={platform} onChange={(event) => setPlatform(event.target.value)}>
          <option value="all">All platforms</option>
          <option value="swiggy">Swiggy</option>
          <option value="zomato">Zomato</option>
          <option value="magicpin">Magicpin</option>
        </select>
        <select className="h-10 rounded-md border border-border bg-input px-2 text-sm" value={type} onChange={(event) => setType(event.target.value)}>
          <option value="all">All types</option>
          <option value="restaurant">Restaurant</option>
          <option value="dineout">Dineout</option>
        </select>
        <select className="h-10 rounded-md border border-border bg-input px-2 text-sm" value={locationMatch} onChange={(event) => setLocationMatch(event.target.value)}>
          <option value="all">All location scopes</option>
          <option value="located_here">Located here</option>
          <option value="delivers_here">Delivers here</option>
          <option value="unknown">Location unknown</option>
        </select>
        <select className="h-10 rounded-md border border-border bg-input px-2 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="all">All statuses</option>
          <option value="completed">Completed</option>
          <option value="queued">Pending</option>
          <option value="failed">Failed</option>
          <option value="blocked">Blocked</option>
          <option value="skipped">Skipped</option>
        </select>
      </div>

      <div className="flex flex-wrap gap-2">
        {review ? (
          <>
            <Button type="button" variant="outline" onClick={() => selectAll(true)}>
              Select All
            </Button>
            <Button type="button" variant="outline" onClick={() => selectAll(false)}>
              Clear All
            </Button>
            <Button type="button" onClick={() => void start()} disabled={busy}>
              Start Scraping
            </Button>
          </>
        ) : null}
        {scraping ? (
          <Button type="button" variant="outline" onClick={() => void cancel()} disabled={busy}>
            Cancel scraping
          </Button>
        ) : null}
        {canDeleteDiscoveryJob(job.status) ? (
          <DeleteDiscoveryJobButton job={job} organizationId={organizationId} redirectTo="/areas" />
        ) : null}
      </div>

      <ul className="divide-y divide-border rounded-xl border border-border">
        {rows.map((venue) => {
          const key = venue.identity_key || venue.venue_url;
          return (
            <li key={key} className="flex flex-col gap-2 p-4 phone:flex-row phone:items-center phone:justify-between">
              <label className="flex min-w-0 items-start gap-3">
                {review ? (
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={Boolean(selected[key])}
                    onChange={(event) => setSelected((current) => ({ ...current, [key]: event.target.checked }))}
                  />
                ) : null}
                <span className="min-w-0">
                  <span className="block font-medium">{venue.name || venue.venue_url}</span>
                    <span className="block text-sm text-muted-foreground">
                      {isDistanceText(venue.location) ? venue.address || "" : venue.location || venue.address || ""}
                    </span>
                  {venue.rating ? <span className="block text-sm text-muted-foreground">{venue.rating}</span> : null}
                  <span className="block truncate text-xs text-muted-foreground">{venue.venue_url}</span>
                  {venue.existing_catalogue_id ? <span className="block text-xs text-muted-foreground">Already exists</span> : null}
                </span>
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <PlatformBadge platform={venue.platform} />
                <span className={cn("text-xs capitalize text-muted-foreground")}>{venue.catalogue_type}</span>
                <span className="text-xs capitalize">{venue.status}</span>
                <span className="text-xs text-muted-foreground">{locationMatchLabel(venue.location_match)}</span>
                {venue.catalogue_id ? (
                  <Link href={`/catalogues/${venue.catalogue_id}`} className="text-xs underline">
                    Open
                  </Link>
                ) : null}
                {review && venue.existing_catalogue_id ? (
                  <select
                    className="h-8 rounded-md border border-border bg-input px-2 text-xs"
                    value={actions[key] || "skip"}
                    onChange={(event) =>
                      setActions((current) => ({ ...current, [key]: event.target.value as "skip" | "rescrape" | "update" }))
                    }
                  >
                    <option value="skip">Skip</option>
                    <option value="rescrape">Re-scrape</option>
                    <option value="update">Update</option>
                  </select>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
      {pages > 1 ? (
        <div className="flex items-center gap-2 text-sm">
          <Button type="button" variant="outline" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
            Previous
          </Button>
          <span>
            Page {page} of {pages}
          </span>
          <Button type="button" variant="outline" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>
            Next
          </Button>
        </div>
      ) : null}
    </div>
  );
}
