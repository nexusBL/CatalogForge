"use client";

import Container from "@/components/container";
import { CreateCatalogueForm } from "@/components/create-catalogue-form";
import { DashboardShell } from "@/components/dashboard-shell";
import { PageLoadingSkeleton } from "@/components/loading-skeleton";
import { authClient } from "@/lib/auth-client";
import { isAuthenticatedSession } from "@/lib/auth-guard";

export default function CreateCataloguePage() {
  const { data: session, isPending: sessionPending } = authClient.useSession();
  const { data: organizations, isPending: organizationsPending } = authClient.useListOrganizations();
  const organizationId = organizations?.[0]?.id;
  const sessionReady = !sessionPending && isAuthenticatedSession(session);

  return (
    <DashboardShell title="Create Catalogue">
      <Container className="py-6">
        {sessionPending || organizationsPending ? (
          <PageLoadingSkeleton />
        ) : !sessionReady ? (
          <p className="text-sm text-muted-foreground">You need to sign in before using catalogues.</p>
        ) : organizationId ? (
          <CreateCatalogueForm organizationId={organizationId} />
        ) : (
          <p className="text-sm text-muted-foreground">Create a restaurant organization first.</p>
        )}
      </Container>
    </DashboardShell>
  );
}
