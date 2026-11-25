"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AreaJobView } from "@/components/area-job-view";
import Container from "@/components/container";
import { DashboardShell } from "@/components/dashboard-shell";
import { authClient } from "@/lib/auth-client";
import { getAreaJobApi } from "@/lib/catalog-api";
import type { AreaJob } from "@/lib/area-jobs";

export default function AreaJobPage() {
  const params = useParams<{ id: string }>();
  const { data: organizations } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const [job, setJob] = useState<AreaJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId || !params.id) {
      return;
    }
    getAreaJobApi(params.id, organizationId)
      .then((row) => setJob(row))
      .catch(() => setError("Could not load this area job."));
  }, [organizationId, params.id]);

  return (
    <DashboardShell title="Area job">
      <Container className="py-6">
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {job && organizationId ? <AreaJobView job={job} organizationId={organizationId} /> : null}
        {!job && !error ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
      </Container>
    </DashboardShell>
  );
}
