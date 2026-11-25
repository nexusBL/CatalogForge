import type { StoredCatalogue } from "@/lib/catalog-types";

const KEY = "catalogforge.catalogues";

export const CATALOGUES_CHANGED_EVENT = "catalogforge:catalogues-changed";

function canUseStorage(): boolean {
  return typeof window !== "undefined";
}

function notifyCataloguesChanged(organizationId: string): void {
  if (!canUseStorage() || typeof window.dispatchEvent !== "function") {
    return;
  }
  window.dispatchEvent(new CustomEvent(CATALOGUES_CHANGED_EVENT, { detail: { organizationId } }));
}

export function listCatalogues(organizationId: string): StoredCatalogue[] {
  if (!canUseStorage()) {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(KEY);
    const all = raw ? (JSON.parse(raw) as StoredCatalogue[]) : [];
    return all.filter((item) => item.organizationId === organizationId);
  } catch {
    return [];
  }
}

export function saveCatalogue(entry: StoredCatalogue): void {
  if (!canUseStorage()) {
    return;
  }
  const raw = window.localStorage.getItem(KEY);
  const all = raw ? (JSON.parse(raw) as StoredCatalogue[]) : [];
  const rest = all.filter((item) => !(item.id === entry.id && item.organizationId === entry.organizationId));
  window.localStorage.setItem(KEY, JSON.stringify([entry, ...rest]));
  notifyCataloguesChanged(entry.organizationId);
}

export function getCatalogue(id: string, organizationId: string): StoredCatalogue | undefined {
  return listCatalogues(organizationId).find((item) => item.id === id);
}

export function removeCatalogue(id: string, organizationId: string): void {
  if (!canUseStorage()) {
    return;
  }
  const raw = window.localStorage.getItem(KEY);
  const all = raw ? (JSON.parse(raw) as StoredCatalogue[]) : [];
  window.localStorage.setItem(
    KEY,
    JSON.stringify(all.filter((item) => !(item.id === id && item.organizationId === organizationId))),
  );
  notifyCataloguesChanged(organizationId);
}
