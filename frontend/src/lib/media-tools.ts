import type { MediaOperation } from "@/lib/media-types";

export type MediaToolId = "crop" | "enhance" | "background" | "edit" | "cleanup" | "generate";

export type MediaTool = {
  id: MediaToolId;
  operation: MediaOperation;
  label: string;
  title: string;
  description: string;
};

export const MEDIA_TOOLS: MediaTool[] = [
  {
    id: "crop",
    operation: "crop",
    label: "Crop",
    title: "Crop",
    description: "Tighten the frame around the dish. Baba previews a crop; the catalogue photo is not replaced.",
  },
  {
    id: "enhance",
    operation: "enhance",
    label: "Enhance",
    title: "AI Enhance",
    description: "Increase clarity of this dish photo.",
  },
  {
    id: "background",
    operation: "background_removal",
    label: "Background",
    title: "AI Backgrounds",
    description: "Place this dish into a cleaner listing scene.",
  },
  {
    id: "edit",
    operation: "edit",
    label: "AI Edit",
    title: "AI Edit",
    description: "Describe what should change. Baba keeps the dish and only edits what you ask for.",
  },
  {
    id: "cleanup",
    operation: "cleanup",
    label: "Cleanup",
    title: "Cleanup",
    description: "Remove small distractions around the dish. Preview only.",
  },
  {
    id: "generate",
    operation: "generate_image",
    label: "Generate",
    title: "Generate Image",
    description: "Create a listing photo from the item name, description, and a restaurant reference when available.",
  },
];

export function toolsForItem(hasUsableImage: boolean): MediaTool[] {
  if (!hasUsableImage) {
    return MEDIA_TOOLS.filter((row) => row.id === "generate" || row.id === "edit");
  }
  return MEDIA_TOOLS.filter((row) => row.id !== "generate");
}

export function toolForOperation(operation: MediaOperation, hasUsableImage: boolean): MediaTool {
  const tools = toolsForItem(hasUsableImage);
  return tools.find((row) => row.operation === operation) || tools[0];
}
