"use client";

import { useState, type ReactNode } from "react";
import { CatalogueImage } from "@/components/catalogue-image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toolForOperation, toolsForItem, type MediaToolId } from "@/lib/media-tools";
import { artifactUrl, imageOperationsForItem, OPERATION_LABELS, type MediaStudioTab } from "@/lib/media-ui";
import type { MediaJob, MediaOperation, MediaReference, MediaStudioResponse, MediaWorkspaceItem } from "@/lib/media-types";
import { cn } from "@/lib/utils";

const SCENE_PRESETS = [
  "Warm kitchen",
  "Clean studio",
  "Restaurant table",
  "Outdoor daylight",
  "Rustic marble",
  "Elegantly lit wood",
];

const COLOR_SWATCHES = [
  { name: "White", hex: "#FFFFFF" },
  { name: "Charcoal", hex: "#262626" },
  { name: "Mint", hex: "#D1F2D9" },
  { name: "Soft Blue", hex: "#D0E1FD" },
  { name: "Pale Lavender", hex: "#E2D5F8" },
  { name: "Soft Pink", hex: "#FFD6E8" },
  { name: "Soft Peach", hex: "#FFE5D9" },
];

function jobsForPath(jobs: MediaJob[], path: string): MediaJob[] {
  return jobs.filter((job) => job.path === path);
}

function activeWorkspaceJob(item: MediaWorkspaceItem | null, jobs: MediaJob[]): MediaJob | null {
  if (!item) {
    return null;
  }
  if (item.active_job_id) {
    return jobs.find((job) => job.id === item.active_job_id) || null;
  }
  return jobs.find((job) => job.status === "READY" && job.active_candidate_id) || null;
}

function Frame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-2 flex min-h-48 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted/30">
        {children}
      </div>
    </div>
  );
}

export function MediaStudioView({
  catalogueId,
  organizationId,
  studio,
  selectedPath,
  tab,
  operation,
  prompt,
  generating,
  error,
  onSelectPath,
  onTab,
  onOperation,
  onPrompt,
  onGenerate,
  onAssist,
  onRevert,
  onApplyLive,
  applying = false,
}: {
  catalogueId: string;
  organizationId: string;
  studio: MediaStudioResponse | null;
  selectedPath: string | null;
  tab: MediaStudioTab;
  operation: MediaOperation;
  prompt: string;
  generating: boolean;
  error: string | null;
  onSelectPath: (path: string) => void;
  onTab: (tab: MediaStudioTab) => void;
  onOperation: (operation: MediaOperation) => void;
  onPrompt: (value: string) => void;
  onGenerate: (operation?: MediaOperation) => void;
  onAssist: () => void;
  onRevert: () => void;
  onApplyLive?: () => void;
  applying?: boolean;
}) {
  // Fine-tuning state for AI Enhance & Backgrounds (Vela studio style)
  const [enhancePreset, setEnhancePreset] = useState<"detailed" | "neat" | "magic">("detailed");
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(0);
  const [saturation, setSaturation] = useState(0);
  const [gamma, setGamma] = useState(0);
  const [clarity, setClarity] = useState(0);

  // Background controls
  const [bgTab, setBgTab] = useState<"colors" | "photos">("colors");
  const [bgBlur, setBgBlur] = useState(0);
  const [bgColor, setBgColor] = useState("#FFFFFF");

  // Crop aspect preset
  const [cropAspect, setCropAspect] = useState<"1:1" | "4:3" | "16:9" | "3:4">("1:1");

  const item = studio?.items.find((row) => row.path === selectedPath) || null;
  const pathJobs = selectedPath ? jobsForPath(studio?.jobs || [], selectedPath) : [];
  const active = activeWorkspaceJob(item, pathJobs);
  const candidate = active?.candidates.find((row) => row.id === active.active_candidate_id) || active?.candidates[0];
  const references: MediaReference[] = studio?.references || [];
  const afterIsGif =
    Boolean(candidate) &&
    (candidate?.content_type === "image/gif" ||
      (candidate?.media_kind === "video" && Boolean(candidate.content_type.startsWith("image/"))));
  const tools = item ? toolsForItem(item.has_usable_image) : [];
  const tool = item ? toolForOperation(operation, item.has_usable_image) : null;
  const toolId: MediaToolId | null = tab === "gifs" ? null : tool?.id || null;
  const originalSrc = active?.original_artifact_id
    ? artifactUrl(catalogueId, organizationId, active.original_artifact_id)
    : item?.image_url;
  const candidateSrc = candidate ? artifactUrl(catalogueId, organizationId, candidate.artifact_id) : null;
  const canRun = Boolean(item) && !(tab === "gifs" && !item?.has_usable_image);

  // Live CSS filter calculation based on sliders
  const activeFilter =
    afterIsGif || tab === "gifs"
      ? "none"
      : `brightness(${100 + brightness}%) contrast(${100 + contrast}%) saturate(${100 + saturation}%) blur(${bgBlur / 10}px)`;

  const resetSliders = () => {
    setBrightness(0);
    setContrast(0);
    setSaturation(0);
    setGamma(0);
    setClarity(0);
    setBgBlur(0);
    setBgColor("#FFFFFF");
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[13rem_minmax(0,1fr)]">
      <aside className="space-y-3 rounded-lg border border-border bg-background p-3">
        <h2 className="text-sm font-medium">Catalogue items</h2>
        <ul className="max-h-[70vh] space-y-1 overflow-y-auto">
          {(studio?.items || []).map((row: MediaWorkspaceItem) => (
            <li key={row.path}>
              <button
                type="button"
                onClick={() => {
                  onSelectPath(row.path);
                  resetSliders();
                }}
                className={cn(
                  "w-full rounded-md px-2 py-1.5 text-left text-sm",
                  selectedPath === row.path ? "bg-selected text-foreground" : "text-muted-foreground hover:bg-selected",
                )}
              >
                <span className="block truncate">{row.name}</span>
                <span className="block text-[11px]">{row.has_usable_image ? "Has image" : "Missing image"}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="overflow-hidden rounded-lg border border-border bg-background">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant={tab === "images" ? "default" : "outline"} onClick={() => onTab("images")}>
              Images
            </Button>
            <Button type="button" size="sm" variant={tab === "gifs" ? "default" : "outline"} onClick={() => onTab("gifs")}>
              GIF Creation
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={resetSliders}
              title="Reset sliders"
              className="text-xs text-muted-foreground"
            >
              ↺ Reset filters
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                resetSliders();
                onRevert();
              }}
              disabled={generating || !item}
            >
              Revert to original
            </Button>
            {active && active.status === "READY" && active.active_candidate_id && onApplyLive ? (
              <Button type="button" size="sm" onClick={onApplyLive} disabled={applying || generating}>
                {applying ? "Applying…" : "Apply to catalogue"}
              </Button>
            ) : (
              <Button type="button" size="sm" variant="outline" disabled title="Generate or select a media preview to apply.">
                Apply to catalogue
              </Button>
            )}
          </div>
        </header>

        {error ? <p className="px-3 pt-3 text-sm text-destructive">{error}</p> : null}

        {!item ? (
          <p className="p-4 text-sm text-muted-foreground">Select a catalogue item to generate or improve media.</p>
        ) : (
          <div className="grid min-h-[34rem] lg:grid-cols-[4.5rem_21rem_minmax(0,1fr)]">
            {tab === "images" ? (
              <nav className="flex flex-row gap-1 overflow-x-auto border-b border-border p-2 lg:flex-col lg:border-b-0 lg:border-r" aria-label="Image tools">
                {tools.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    title={row.label}
                    aria-label={row.label}
                    aria-current={toolId === row.id ? "true" : undefined}
                    onClick={() => onOperation(row.operation)}
                    className={cn(
                      "flex flex-col items-center justify-center rounded-lg p-2 text-center text-[10px] font-medium transition-colors",
                      toolId === row.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-selected",
                    )}
                  >
                    <span className="text-base">
                      {row.id === "crop"
                        ? "✂️"
                        : row.id === "enhance"
                        ? "✨"
                        : row.id === "background"
                        ? "🖼️"
                        : row.id === "cleanup"
                        ? "🧹"
                        : "🎨"}
                    </span>
                    <span className="mt-1">{row.label}</span>
                  </button>
                ))}
                <span className="sr-only">{imageOperationsForItem(item.has_usable_image).map((row) => row.label).join(" ")}</span>
              </nav>
            ) : (
              <div className="hidden border-r border-border lg:block" />
            )}

            <div className="space-y-4 border-b border-border p-4 lg:border-b-0 lg:border-r max-h-[80vh] overflow-y-auto">
              <div>
                <h2 className="text-base font-semibold">{tab === "images" ? "AI Image Improvement" : "GIF Creation"}</h2>
                <p className="text-xs text-muted-foreground">
                  {item.name} · {item.category_name}
                </p>
                <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{item.description || "No description."}</p>
              </div>

              {tab === "gifs" ? (
                <>
                  <p className="text-xs text-muted-foreground">
                    Turn a catalogue image into a short animated GIF. This is a motion preview, not AI video, and it does not write
                    venue videos.
                  </p>
                  <Button type="button" className="w-full" onClick={() => onGenerate()} disabled={generating || !item.has_usable_image}>
                    {generating ? "Generating…" : "Create GIF"}
                  </Button>
                </>
              ) : toolId === "enhance" ? (
                <div className="space-y-4">
                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3">
                    <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">{tool?.title || "AI Enhance"}</p>
                    <p className="mt-1 text-xs text-muted-foreground">Increase image resolution and clarity</p>
                    <Button
                      type="button"
                      className="mt-3 w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                      onClick={() => {
                        const enhPrompt = `Enhance image with ${enhancePreset} preset. Brightness: ${brightness}, Contrast: ${contrast}, Saturation: ${saturation}, Clarity: ${clarity}`;
                        if (enhPrompt) onPrompt(enhPrompt);
                        onGenerate("enhance");
                      }}
                      disabled={generating || !canRun}
                    >
                      {generating ? "Enhancing…" : "✨ Enhance"}
                    </Button>
                  </div>

                  {/* Feature status checks */}
                  <div className="space-y-2 rounded-lg border border-border p-3 text-xs bg-muted/20">
                    <div className="flex items-center justify-between">
                      <span>Fixing details</span>
                      <span className="text-emerald-500">✓ Ready</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Reducing blur</span>
                      <span className="text-emerald-500">✓ Ready</span>
                    </div>
                    <div className="flex items-center justify-between font-medium">
                      <span>Sharpen details</span>
                      <span className="text-emerald-500">✓ Active</span>
                    </div>
                  </div>

                  {/* Preset Selector Cards */}
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-2">Preset Modes</p>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: "detailed", label: "Detailed", desc: "Sharpen" },
                        { id: "neat", label: "Neat", desc: "Clean" },
                        { id: "magic", label: "Magic", desc: "Vivid" },
                      ].map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => {
                            setEnhancePreset(p.id as any);
                            if (p.id === "detailed") {
                              setClarity(20);
                              setContrast(10);
                            } else if (p.id === "neat") {
                              setClarity(5);
                              setContrast(5);
                              setSaturation(-5);
                            } else {
                              setClarity(30);
                              setContrast(15);
                              setSaturation(15);
                            }
                          }}
                          className={cn(
                            "flex flex-col items-center justify-center rounded-lg border p-2 text-center transition-all",
                            enhancePreset === p.id
                              ? "border-emerald-500 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium"
                              : "border-border hover:bg-muted text-muted-foreground",
                          )}
                        >
                          <span className="text-xs">{p.label}</span>
                          <span className="text-[10px] opacity-75">{p.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Fine-Tuning Sliders (Vela Studio Style) */}
                  <div className="space-y-3 rounded-lg border border-border p-3 bg-muted/10">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Adjustments</p>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Brightness</span>
                        <span className="text-muted-foreground">{brightness > 0 ? `+${brightness}` : brightness}</span>
                      </div>
                      <input
                        type="range"
                        min="-50"
                        max="50"
                        value={brightness}
                        onChange={(e) => setBrightness(Number(e.target.value))}
                        className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Contrast</span>
                        <span className="text-muted-foreground">{contrast > 0 ? `+${contrast}` : contrast}</span>
                      </div>
                      <input
                        type="range"
                        min="-50"
                        max="50"
                        value={contrast}
                        onChange={(e) => setContrast(Number(e.target.value))}
                        className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Saturation</span>
                        <span className="text-muted-foreground">{saturation > 0 ? `+${saturation}` : saturation}</span>
                      </div>
                      <input
                        type="range"
                        min="-50"
                        max="50"
                        value={saturation}
                        onChange={(e) => setSaturation(Number(e.target.value))}
                        className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Gamma</span>
                        <span className="text-muted-foreground">{gamma > 0 ? `+${gamma}` : gamma}</span>
                      </div>
                      <input
                        type="range"
                        min="-50"
                        max="50"
                        value={gamma}
                        onChange={(e) => setGamma(Number(e.target.value))}
                        className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Clarity</span>
                        <span className="text-muted-foreground">{clarity > 0 ? `+${clarity}` : clarity}</span>
                      </div>
                      <input
                        type="range"
                        min="-50"
                        max="50"
                        value={clarity}
                        onChange={(e) => setClarity(Number(e.target.value))}
                        className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
                      />
                    </div>

                    <Button
                      type="button"
                      className="mt-3 w-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold"
                      onClick={() => {
                        const adjPrompt = `Apply adjustments: brightness: ${brightness > 0 ? `+${brightness}` : brightness}, contrast: ${contrast > 0 ? `+${contrast}` : contrast}, saturation: ${saturation > 0 ? `+${saturation}` : saturation}, clarity: ${clarity > 0 ? `+${clarity}` : clarity}, blur: ${bgBlur}`;
                        onPrompt(adjPrompt);
                        onGenerate("edit");
                        resetSliders();
                      }}
                      disabled={generating || !canRun}
                    >
                      {generating ? "Applying Adjustments…" : "✓ Apply Adjustments (Done)"}
                    </Button>
                  </div>
                </div>
              ) : toolId === "background" ? (
                <div className="space-y-4">
                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3">
                    <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">{tool?.title || "AI Backgrounds"}</p>
                    <p className="mt-1 text-xs text-muted-foreground">Place products into beautiful scenes</p>
                    <Button
                      type="button"
                      className="mt-3 w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                      onClick={() => onGenerate("background_removal")}
                      disabled={generating || !canRun}
                    >
                      {generating ? "Removing…" : "✨ Remove Background"}
                    </Button>
                  </div>

                  {/* Background Blur Slider */}
                  <div className="space-y-2 rounded-lg border border-border p-3 bg-muted/10">
                    <div className="flex justify-between text-xs font-medium">
                      <span>Background blur</span>
                      <span className="text-muted-foreground">{bgBlur}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={bgBlur}
                      onChange={(e) => setBgBlur(Number(e.target.value))}
                      className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-emerald-500"
                    />
                  </div>

                  {/* Standard Generate (Colors / Photos) */}
                  <div className="rounded-lg border border-border p-3 space-y-3">
                    <div className="flex items-center justify-between border-b border-border pb-2">
                      <span className="text-xs font-semibold">Standard Backgrounds</span>
                      <div className="flex rounded-md bg-muted p-0.5 text-[10px]">
                        <button
                          type="button"
                          onClick={() => setBgTab("colors")}
                          className={cn("px-2 py-0.5 rounded", bgTab === "colors" ? "bg-background font-semibold shadow-xs" : "text-muted-foreground")}
                        >
                          Colors
                        </button>
                        <button
                          type="button"
                          onClick={() => setBgTab("photos")}
                          className={cn("px-2 py-0.5 rounded", bgTab === "photos" ? "bg-background font-semibold shadow-xs" : "text-muted-foreground")}
                        >
                          Photos
                        </button>
                      </div>
                    </div>

                    {bgTab === "colors" ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={bgColor}
                            onChange={(e) => setBgColor(e.target.value)}
                            className="h-7 w-7 rounded cursor-pointer border border-border p-0 bg-transparent"
                          />
                          <Input
                            value={bgColor}
                            onChange={(e) => setBgColor(e.target.value)}
                            className="h-7 font-mono text-xs uppercase"
                            placeholder="#FFFFFF"
                          />
                        </div>

                        <div className="flex flex-wrap gap-1.5">
                          {COLOR_SWATCHES.map((swatch) => (
                            <button
                              key={swatch.name}
                              type="button"
                              title={swatch.name}
                              onClick={() => {
                                setBgColor(swatch.hex);
                                onPrompt(`Set solid ${swatch.name} (${swatch.hex}) background behind dish`);
                              }}
                              className={cn(
                                "h-6 w-6 rounded-full border border-border shadow-xs transition-transform hover:scale-110",
                                bgColor.toLowerCase() === swatch.hex.toLowerCase() ? "ring-2 ring-emerald-500 ring-offset-1" : "",
                              )}
                              style={{ backgroundColor: swatch.hex }}
                            />
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">Select from studio reference photos below or describe a scene.</p>
                    )}
                  </div>

                  {/* AI Generate Scene */}
                  <div className="space-y-2">
                    <p className="text-xs font-semibold">AI Scene Prompt</p>
                    <p className="text-[11px] text-muted-foreground">Describe the scene around your dish.</p>
                    <div className="flex flex-wrap gap-1">
                      {SCENE_PRESETS.map((preset) => (
                        <Button
                          key={preset}
                          type="button"
                          size="sm"
                          variant="outline"
                          className="text-[11px] h-6 px-2"
                          onClick={() => {
                            onPrompt(`${preset} behind the dish, keep the dish unchanged.`);
                            onOperation("background_generation");
                          }}
                        >
                          {preset}
                        </Button>
                      ))}
                    </div>
                    <label className="block space-y-1 text-xs">
                      <span className="sr-only">Tell Baba what you want to change</span>
                      <Input
                        value={prompt}
                        onChange={(event) => onPrompt(event.target.value)}
                        placeholder="Add a warm rustic Italian kitchen behind the dish while keeping the dish unchanged."
                        aria-label="Tell Baba what you want to change"
                      />
                    </label>
                    <div className="flex gap-2 pt-1">
                      <Button
                        type="button"
                        variant="default"
                        size="sm"
                        className="flex-1 text-xs"
                        onClick={() => onGenerate("background_generation")}
                        disabled={generating || !canRun}
                      >
                        {generating ? "Generating…" : "Generate Background"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="text-xs"
                        onClick={() => onGenerate("blur")}
                        disabled={generating || !canRun}
                      >
                        Blur
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="text-xs"
                        onClick={() => onGenerate("expand")}
                        disabled={generating || !canRun}
                      >
                        Expand
                      </Button>
                    </div>
                  </div>
                </div>
              ) : toolId === "crop" ? (
                <div className="space-y-4">
                  <p className="text-xs text-muted-foreground">{tool?.description || "Tighten the frame around the dish."}</p>
                  <div>
                    <p className="text-xs font-medium mb-1">Aspect Ratio Presets</p>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { id: "1:1", label: "1:1 Square" },
                        { id: "4:3", label: "4:3 Standard" },
                        { id: "16:9", label: "16:9 Landscape" },
                        { id: "3:4", label: "3:4 Portrait" },
                      ].map((ratio) => (
                        <button
                          key={ratio.id}
                          type="button"
                          onClick={() => setCropAspect(ratio.id as any)}
                          className={cn(
                            "rounded-md border p-2 text-center text-xs transition-colors",
                            cropAspect === ratio.id ? "border-primary bg-primary/10 font-medium" : "border-border hover:bg-muted",
                          )}
                        >
                          {ratio.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <Button type="button" className="w-full" onClick={() => onGenerate("crop")} disabled={generating || !canRun}>
                    {generating ? "Generating…" : "Crop"}
                  </Button>
                </div>
              ) : toolId === "cleanup" ? (
                <div className="space-y-4">
                  <p className="text-xs text-muted-foreground">{tool?.description || "Remove spots, reflections and clean up imperfections."}</p>
                  <Button type="button" className="w-full" onClick={() => onGenerate("cleanup")} disabled={generating || !canRun}>
                    {generating ? "Generating…" : "Cleanup"}
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {!item.has_usable_image ? (
                    <p className="text-xs text-muted-foreground">
                      Generate Image uses the item name, description, and one catalogue reference photo when available. Results stay
                      preview-only.
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">{tool?.description}</p>
                  )}
                  <label className="block space-y-1 text-xs">
                    <span>Tell Baba what you want to change</span>
                    <Input
                      value={prompt}
                      onChange={(event) => onPrompt(event.target.value)}
                      placeholder="Add a warm rustic Italian kitchen behind the dish while keeping the dish unchanged."
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {item.has_usable_image ? (
                      <Button type="button" onClick={() => onGenerate()} disabled={generating}>
                        {generating ? "Generating…" : OPERATION_LABELS[operation] || "Generate"}
                      </Button>
                    ) : (
                      <Button type="button" onClick={() => onGenerate("generate_image")} disabled={generating}>
                        {generating ? "Generating…" : "Generate Image"}
                      </Button>
                    )}
                    <Button type="button" variant="outline" onClick={onAssist} disabled={generating}>
                      Prompt assistance
                    </Button>
                  </div>
                </div>
              )}

              {!item.has_usable_image && references.length && tab === "images" ? (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Restaurant reference images</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {references.map((ref) => (
                      <div key={ref.path} className="w-24">
                        <CatalogueImage src={ref.image_url} alt={ref.name} className="h-20 w-24 object-cover rounded-md border border-border" fallbackClassName="h-20 w-24" />
                        <p className="truncate text-[11px] text-muted-foreground mt-1">{ref.name}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              <p className="text-[11px] text-muted-foreground">
                Candidates stay preview-only until you apply them to the live catalogue.
              </p>
              {onApplyLive && candidate && active?.status === "READY" ? (
                <Button type="button" className="w-full" onClick={onApplyLive} disabled={generating || applying}>
                  {applying ? "Applying to catalogue…" : "Apply to live catalogue"}
                </Button>
              ) : null}
            </div>

            <div className="space-y-4 p-4">
              <div className="flex min-h-[22rem] items-center justify-center rounded-xl border border-border bg-muted/20 p-4 relative overflow-hidden">
                {candidateSrc && candidate ? (
                  candidate.media_kind === "video" && candidate.content_type.startsWith("video/") ? (
                    <video className="max-h-[28rem] w-full" controls src={candidateSrc} />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      alt={afterIsGif ? "GIF preview" : "Generated"}
                      className="max-h-[28rem] w-full object-contain transition-all duration-200"
                      src={candidateSrc}
                      style={{ filter: activeFilter }}
                    />
                  )
                ) : originalSrc ? (
                  <CatalogueImage src={originalSrc} alt={item.name} className="max-h-[28rem] w-full object-contain" />
                ) : (
                  <p className="text-sm text-muted-foreground">No source image.</p>
                )}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Frame label={tab === "gifs" ? "Original" : "Before"}>
                  {originalSrc ? (
                    active?.original_artifact_id ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img alt="Original" className="max-h-56 w-full object-contain" src={originalSrc} />
                    ) : (
                      <CatalogueImage src={originalSrc} alt={item.name} className="max-h-56 w-full object-contain" />
                    )
                  ) : (
                    <p className="p-4 text-sm text-muted-foreground">No source image.</p>
                  )}
                </Frame>
                <Frame label={tab === "gifs" ? "GIF preview" : "After"}>
                  {candidateSrc && candidate ? (
                    candidate.media_kind === "video" && candidate.content_type.startsWith("video/") ? (
                      <video className="max-h-56 w-full" controls src={candidateSrc} />
                    ) : (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        alt={afterIsGif ? "GIF preview" : "Generated"}
                        className="max-h-56 w-full object-contain transition-all duration-200"
                        src={candidateSrc}
                        style={{ filter: activeFilter }}
                      />
                    )
                  ) : (
                    <p className="p-4 text-sm text-muted-foreground">No generated candidate yet. Catalogue media is unchanged.</p>
                  )}
                </Frame>
              </div>
              {active ? (
                <p className="text-xs text-muted-foreground">
                  Status: <span className="font-semibold">{active.status}</span>
                  {active.error ? ` · ${active.error}` : ""}
                </p>
              ) : null}
              {pathJobs.length ? (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Revision history</p>
                  <ul className="mt-2 space-y-1 text-xs">
                    {pathJobs.map((job) => (
                      <li key={job.id} className="text-muted-foreground">
                        {OPERATION_LABELS[job.operation] || job.operation} · {job.status} · {job.candidates.length} candidate(s)
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
