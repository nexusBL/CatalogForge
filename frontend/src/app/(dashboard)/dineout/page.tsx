"use client";

import { DomainCatalogueList } from "@/components/domain-catalogue-list";

export default function DineoutPage() {
  return (
    <DomainCatalogueList
      title="My Dineout"
      domain="dineout"
      empty="No Dineout catalogues yet. Create a Dineout catalogue to see venues here."
    />
  );
}
