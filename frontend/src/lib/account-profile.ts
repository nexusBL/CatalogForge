export type AccountProfile = {
  photoDataUrl: string;
  fullName: string;
  email: string;
  phone: string;
  whatsapp: string;
  city: string;
  bio: string;
  linkedin: string;
  instagram: string;
  companyName: string;
  role: string;
  businessAddress: string;
  website: string;
  businessDescription: string;
  gstin: string;
};

export type NotificationPrefs = {
  catalogueReady: boolean;
  extractionFailed: boolean;
  productUpdates: boolean;
};

export const EMPTY_PROFILE: AccountProfile = {
  photoDataUrl: "",
  fullName: "",
  email: "",
  phone: "",
  whatsapp: "",
  city: "",
  bio: "",
  linkedin: "",
  instagram: "",
  companyName: "",
  role: "",
  businessAddress: "",
  website: "",
  businessDescription: "",
  gstin: "",
};

export const DEFAULT_NOTIFICATIONS: NotificationPrefs = {
  catalogueReady: true,
  extractionFailed: true,
  productUpdates: false,
};

export function profileStorageKey(userId: string | null | undefined): string {
  return `hecto-baba-profile:${userId || "local"}`;
}

export function notificationStorageKey(userId: string | null | undefined): string {
  return `hecto-baba-notifications:${userId || "local"}`;
}

export function parseAccountProfile(raw: string | null): AccountProfile {
  if (!raw) {
    return { ...EMPTY_PROFILE };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AccountProfile>;
    return { ...EMPTY_PROFILE, ...parsed };
  } catch {
    return { ...EMPTY_PROFILE };
  }
}

export function parseNotificationPrefs(raw: string | null): NotificationPrefs {
  if (!raw) {
    return { ...DEFAULT_NOTIFICATIONS };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<NotificationPrefs>;
    return { ...DEFAULT_NOTIFICATIONS, ...parsed };
  } catch {
    return { ...DEFAULT_NOTIFICATIONS };
  }
}

export function loadAccountProfile(userId: string | null | undefined): AccountProfile {
  if (typeof window === "undefined") {
    return { ...EMPTY_PROFILE };
  }
  return parseAccountProfile(window.localStorage.getItem(profileStorageKey(userId)));
}

export function saveAccountProfile(userId: string | null | undefined, profile: AccountProfile): void {
  window.localStorage.setItem(profileStorageKey(userId), JSON.stringify(profile));
}

export function loadNotificationPrefs(userId: string | null | undefined): NotificationPrefs {
  if (typeof window === "undefined") {
    return { ...DEFAULT_NOTIFICATIONS };
  }
  return parseNotificationPrefs(window.localStorage.getItem(notificationStorageKey(userId)));
}

export function saveNotificationPrefs(userId: string | null | undefined, prefs: NotificationPrefs): void {
  window.localStorage.setItem(notificationStorageKey(userId), JSON.stringify(prefs));
}

export function profileHeadline(profile: AccountProfile): string | null {
  const role = profile.role.trim();
  const company = profile.companyName.trim();
  if (role && company) {
    return `${role} · ${company}`;
  }
  return role || company || null;
}
