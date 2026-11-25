import type { MediaOperation } from "@/lib/media-types";

export const IMAGE_OPERATIONS: Array<{ id: MediaOperation; label: string }> = [
  { id: "generate_image", label: "Generate Image" },
  { id: "edit", label: "AI Edit" },
  { id: "enhance", label: "Enhance" },
  { id: "background_removal", label: "Remove Background" },
  { id: "background_generation", label: "Generate Background" },
  { id: "blur", label: "Blur" },
  { id: "crop", label: "Crop" },
  { id: "expand", label: "Expand" },
  { id: "cleanup", label: "Cleanup" },
];

export const OPERATION_LABELS: Record<MediaOperation, string> = {
  generate_image: "Generate Image",
  edit: "AI Edit",
  enhance: "Enhance",
  background_removal: "Remove Background",
  background_generation: "Generate Background",
  blur: "Blur",
  crop: "Crop",
  expand: "Expand",
  cleanup: "Cleanup",
  image_to_video: "Create GIF",
};

export type MediaStudioTab = "images" | "gifs";

export function imageOperationsForItem(hasUsableImage: boolean): Array<{ id: MediaOperation; label: string }> {
  return IMAGE_OPERATIONS.filter((row) => (hasUsableImage ? row.id !== "generate_image" : row.id === "generate_image" || row.id === "edit"));
}

export function publicMediaError(message: string | null | undefined, tab: MediaStudioTab): string | null {
  if (!message) {
    return null;
  }
  const lowered = message.toLowerCase();
  if (
    lowered.includes("provider") ||
    lowered.includes("quota") ||
    lowered.includes("timed out") ||
    lowered.includes("unavailable") ||
    lowered.includes("malformed")
  ) {
    return tab === "gifs"
      ? "GIF creation is temporarily unavailable. Please try again."
      : "AI image generation is temporarily unavailable. Please try again.";
  }
  return message;
}

export function catalogueMediaHref(catalogueId: string, extras?: { path?: string; proposalId?: string }): string {
  const base = `/catalogues/${catalogueId}/media`;
  const params = new URLSearchParams();
  if (extras?.path) {
    params.set("path", extras.path);
  }
  if (extras?.proposalId) {
    params.set("proposal_id", extras.proposalId);
  }
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

export function artifactUrl(catalogueId: string, organizationId: string, artifactId: string): string {
  return `/api/catalogues/${encodeURIComponent(catalogueId)}/media-artifacts/${encodeURIComponent(artifactId)}?organization_id=${encodeURIComponent(organizationId)}`;
}
