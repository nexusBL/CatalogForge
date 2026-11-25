"use client";

import { DomainCatalogueList } from "@/components/domain-catalogue-list";

export default function RestaurantPage() {
  return (
    <DomainCatalogueList
      title="My Restaurant"
      domain="restaurant"
      empty="No restaurant catalogues yet. Create one from Create Catalogue."
    />
  );
}
