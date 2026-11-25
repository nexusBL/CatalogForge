"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { isAuthenticatedSession } from "@/lib/auth-guard";
import { PageLoadingSkeleton } from "@/components/loading-skeleton";
import { restaurantSlug } from "@/lib/catalog-form";

export function OrganizationGate({ children }: { children: ReactNode }) {
  const { data: session, isPending: sessionPending } = authClient.useSession();
  const { data: organizations, isPending } = authClient.useListOrganizations();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function createRestaurant(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    const slug = restaurantSlug(name);
    const { error: createError } = await authClient.organization.create({
      name: name.trim(),
      slug,
    });
    if (createError) {
      setSaving(false);
      setError(createError.message || "Could not create the restaurant organization.");
      return;
    }
    await authClient.organization.setActive({ organizationSlug: slug });
    setSaving(false);
  }

  if (sessionPending || isPending) {
    return <PageLoadingSkeleton />;
  }
  if (!isAuthenticatedSession(session)) {
    return <p className="p-6 text-sm text-muted-foreground">Checking your session…</p>;
  }
  if (!organizations || organizations.length === 0) {
    return (
      <div className="mx-auto max-w-md space-y-4 p-6">
        <h1 className="text-2xl font-medium">Set up your restaurant</h1>
        <p className="text-sm text-muted-foreground">
          Your restaurant is a CatalogForge organization. You can invite staff later.
        </p>
        <form className="space-y-4" onSubmit={(event) => void createRestaurant(event)}>
          <div className="space-y-2">
            <Label htmlFor="restaurant">Restaurant name</Label>
            <Input
              id="restaurant"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button type="submit" disabled={saving}>
            {saving ? "Creating…" : "Create restaurant"}
          </Button>
        </form>
      </div>
    );
  }
  return <>{children}</>;
}
