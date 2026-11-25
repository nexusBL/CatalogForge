"use client";

import {
  ExternalLinkIcon,
  FileTextIcon,
  HomeIcon,
  MobileIcon,
  SewingPinIcon,
  StarIcon,
} from "@radix-ui/react-icons";
import type { ReactNode } from "react";
import { dineoutAboutFields, looksLikeUrl, restaurantAboutFields, type AboutField } from "@/lib/restaurant-identity";
import type { CatalogueRestaurant, DineoutVenue } from "@/lib/catalog-types";

function FieldIcon({ kind }: { kind?: AboutField["kind"] }) {
  if (kind === "location") {
    return <SewingPinIcon className="mt-0.5 size-4 text-muted-foreground" />;
  }
  if (kind === "license") {
    return <FileTextIcon className="mt-0.5 size-4 text-muted-foreground" />;
  }
  if (kind === "rating") {
    return <StarIcon className="mt-0.5 size-4 text-muted-foreground" />;
  }
  if (kind === "phone") {
    return <MobileIcon className="mt-0.5 size-4 text-muted-foreground" />;
  }
  if (kind === "link") {
    return <ExternalLinkIcon className="mt-0.5 size-4 text-muted-foreground" />;
  }
  return <HomeIcon className="mt-0.5 size-4 text-muted-foreground" />;
}

export function AboutFieldList({ fields, empty }: { fields: AboutField[]; empty: ReactNode }) {
  if (!fields.length) {
    return empty;
  }
  return (
    <dl className="grid gap-4 text-sm laptop:grid-cols-2">
      {fields.map((field) => {
        const href = field.href || (looksLikeUrl(field.value) ? field.value : undefined);
        return (
          <div key={field.label} className="flex gap-2">
            <FieldIcon kind={field.kind} />
            <div className="min-w-0">
              <dt className="text-muted-foreground">{field.label}</dt>
              <dd className="break-all font-medium">
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="underline-offset-4 hover:underline">
                    {field.value}
                  </a>
                ) : (
                  field.value
                )}
              </dd>
            </div>
          </div>
        );
      })}
    </dl>
  );
}

export function AboutFields({
  restaurant,
  restaurantName,
  fssaiNumber,
  sourceUrl,
}: {
  restaurant?: CatalogueRestaurant | null;
  restaurantName?: string;
  fssaiNumber?: string;
  sourceUrl?: string;
}) {
  const fields = restaurantAboutFields({ restaurant, restaurantName, fssaiNumber, sourceUrl });
  return (
    <AboutFieldList
      fields={fields}
      empty={
        <p className="text-sm text-muted-foreground">
          No restaurant details are stored yet. Create a catalogue to capture source data.
        </p>
      }
    />
  );
}

export function DineoutAboutFields({
  venue,
  fallbackUrl,
}: {
  venue?: DineoutVenue | null;
  fallbackUrl?: string;
}) {
  const fields = dineoutAboutFields(venue, fallbackUrl);
  return (
    <AboutFieldList
      fields={fields}
      empty={
        <p className="text-sm text-muted-foreground">
          Dineout details will appear here when a dineout catalogue exists.
        </p>
      }
    />
  );
}
