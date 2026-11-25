export function catalogueAssistantHref(catalogueId: string): string {
  return `/catalogues/${catalogueId}/assistant`;
}

export function babaAiHref(catalogueId?: string | null): string {
  const id = (catalogueId || "").trim();
  if (!id) {
    return "/baba-ai";
  }
  return `/baba-ai?catalogue=${encodeURIComponent(id)}`;
}

export function catalogueIdFromPathname(pathname: string): string | null {
  const grading = /^\/grading\/([^/]+)/.exec(pathname);
  if (grading) {
    return grading[1];
  }
  const match = /^\/catalogues\/([^/]+)/.exec(pathname);
  if (!match) {
    return null;
  }
  const id = match[1];
  if (id === "new") {
    return null;
  }
  return id;
}

export const BABA_AI_PROMPTS = [
  "Why is my catalogue graded C?",
  "What should I fix first?",
  "What are customers complaining about?",
  "Show my recommendations",
] as const;


