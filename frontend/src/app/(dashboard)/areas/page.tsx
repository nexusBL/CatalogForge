"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";
import { DeleteDiscoveryJobButton } from "@/components/delete-discovery-job-button";
import { listAreaJobsApi } from "@/lib/catalog-api";
import { jobLocation, type AreaJob } from "@/lib/area-jobs";
import { platformLabel } from "@/lib/catalog-types";

export default function AreasPage() {
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [jobs, setJobs] = useState<AreaJob[]>([]);
  const [platform, setPlatform] = useState("all");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!organizationId) {
      return;
    }
    listAreaJobsApi(organizationId).then(setJobs).catch(() => setJobs([]));
  }, [organizationId]);

  function reloadJobs() {
    if (!organizationId) {
      return;
    }
    listAreaJobsApi(organizationId).then(setJobs).catch(() => setJobs([]));
  }

  const rows = jobs.filter((job) => {
    if (platform !== "all" && !job.platforms.includes(platform as AreaJob["platforms"][number])) {
      return false;
    }
    if (type !== "all" && job.catalogue_type !== type) {
      return false;
    }
    if (status !== "all" && job.status !== status) {
      return false;
    }
    if (search.trim() && !jobLocation(job).toLowerCase().includes(search.trim().toLowerCase())) {
      return false;
    }
    return true;
  });

  return (
    <DashboardShell title="City / Areas">
      <Container className="space-y-4 py-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">Jobs created from Area / City discovery. Locations come from your searches.</p>
          <Button asChild>
            <Link href="/catalogues/new">Create Catalogue</Link>
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <input className="h-10 rounded-md border border-border bg-input px-3 text-sm" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search location" />
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
            <option value="both">Both</option>
          </select>
          <select className="h-10 rounded-md border border-border bg-input px-2 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="awaiting_confirmation">Pending</option>
            <option value="scraping">Scraping</option>
            <option value="completed">Completed</option>
            <option value="partially_completed">Partial</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <ul className="divide-y divide-border rounded-xl border border-border">
          {rows.map((job) => (
            <li key={job.id} className="flex flex-col gap-1 p-4 phone:flex-row phone:items-center phone:justify-between">
              <div>
                <Link href={`/areas/${job.id}`} className="font-medium hover:underline">
                  {jobLocation(job) || job.id}
                </Link>
                <p className="text-sm text-muted-foreground">
                  {job.platforms.map((item) => platformLabel(item)).join(", ")} · {job.catalogue_type} · {job.discovered_count ?? job.venues.length} venues · {job.completed_count || 0} completed
                </p>
              </div>
              <div className="flex items-center gap-3">
                <p className="text-sm capitalize">{job.status === "failed" ? "Failed" : job.status.replaceAll("_", " ")}</p>
                {job.status === "failed" && organizationId ? (
                  <DeleteDiscoveryJobButton job={job} organizationId={organizationId} onDeleted={reloadJobs} />
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </Container>
    </DashboardShell>
  );
}
