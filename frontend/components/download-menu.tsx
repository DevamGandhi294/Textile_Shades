"use client";

import { ChevronDown, Download } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { designsApi } from "@/lib/api/data";
import { outlineApi } from "@/lib/api/outline";
import type { ExportFormat } from "@/lib/api/types";
import { Button, Dropdown, DropdownContent, DropdownItem, DropdownLabel, DropdownSeparator, DropdownTrigger } from "./ui/primitives";

type Item = { fmt: ExportFormat; label: string; hint: string };

const VECTOR: Item[] = [
  { fmt: "svg", label: "SVG", hint: "Illustrator, Inkscape" },
  { fmt: "eps", label: "EPS", hint: "Wilcom, CorelDRAW" },
  { fmt: "pdf", label: "PDF", hint: "Print, CorelDRAW" },
  { fmt: "dxf", label: "DXF", hint: "Wilcom (mm), CAD" },
];
const BITMAP: Item[] = [
  { fmt: "bmp", label: "BMP", hint: "Auto-digitizing, textile CAD" },
  { fmt: "tiff", label: "TIFF", hint: "Print, CAD" },
  { fmt: "png", label: "PNG", hint: "Transparent paper" },
];
const AI: Item[] = [
  { fmt: "perfect", label: "AI outline (PNG)", hint: "Transparent, one layer" },
  { fmt: "perfect-psd", label: "AI outline + colour layers (PSD)", hint: "Photoshop" },
];
const AI_LAYERS: Item = { fmt: "ai-layers-psd", label: "AI layers (PSD)", hint: "Outline layer per object" };
const LAYERS: Item[] = [
  { fmt: "layers-psd", label: "Colour layers (PSD)", hint: "One layer per colour" },
  { fmt: "layers-svg", label: "Colour layers (SVG)", hint: "One group per colour" },
  { fmt: "layers-zip", label: "Colour layers (PNG zip)", hint: "One PNG per colour" },
];

/**
 * Download ▾. Files are written by the backend from the live image session; without one
 * (the session expired or the design was never opened here) only the saved image can be downloaded.
 */
export function DownloadMenu({
  sid,
  designId,
  formats,
  hasPerfect,
  hasLayers,
  hasAiLayers,
  layersVersionId,
  fallbackImage,
  fallbackName,
  label = "Download",
  primary,
}: {
  sid: string | null;
  designId: string;
  formats?: string[];
  hasPerfect?: boolean;
  hasLayers?: boolean;
  hasAiLayers?: boolean;
  /** A saved image with its layers: its PSD comes from storage, so it works after the image session ends. */
  layersVersionId?: string | null;
  fallbackImage?: string | null;
  fallbackName?: string;
  label?: string;
  primary?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  async function get(fmt: ExportFormat) {
    if (fmt === "ai-layers-psd" && layersVersionId) {
      setBusy(fmt);
      try {
        await outlineApi.savedLayersPsd(layersVersionId);
        await designsApi.recordExport(designId, fmt);
      } catch (e) {
        toast.error((e as Error).message);
      } finally {
        setBusy(null);
      }
      return;
    }
    if (!sid) return;
    setBusy(fmt);
    try {
      await outlineApi.download(sid, fmt);
      await designsApi.recordExport(designId, fmt);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function saveImage() {
    if (!fallbackImage) return;
    const a = document.createElement("a");
    a.href = fallbackImage;
    a.download = `${fallbackName ?? "outline"}${fallbackImage.startsWith("data:image/svg") ? ".svg" : ".png"}`;
    a.click();
  }

  const can = (f: string) => !!sid && (!formats || formats.includes(f));
  const row = (i: Item, enabled: boolean) => (
    <DropdownItem key={i.fmt} disabled={!enabled || !!busy} onSelect={() => get(i.fmt)}>
      <span>{busy === i.fmt ? "Making…" : i.label}</span>
      <span className="text-xs text-muted">{i.hint}</span>
    </DropdownItem>
  );

  return (
    <Dropdown>
      <DropdownTrigger asChild>
        <Button variant={primary ? "primary" : "secondary"} loading={!!busy}>
          <Download className="h-4 w-4" /> {label} <ChevronDown className="h-3.5 w-3.5" />
        </Button>
      </DropdownTrigger>
      <DropdownContent className="w-80">
        {!sid && (
          <p className="px-3 py-2 text-xs text-muted">
            Open this design in the workspace and upload the raw image to make files. The image server keeps a photo for one hour.
          </p>
        )}
        <DropdownLabel>Editable outlines</DropdownLabel>
        {VECTOR.map((i) => row(i, can(i.fmt)))}
        <DropdownLabel>Bitmaps</DropdownLabel>
        {BITMAP.map((i) => row(i, can(i.fmt)))}
        <DropdownSeparator />
        {AI.map((i) => row(i, !!sid && !!hasPerfect))}
        {row(AI_LAYERS, !!layersVersionId || (!!sid && !!hasAiLayers))}
        {LAYERS.map((i) => row(i, !!sid && !!hasLayers))}
        <DropdownSeparator />
        {row({ fmt: "zip", label: "Everything (ZIP)", hint: "All files" }, !!sid)}
        {fallbackImage && (
          <DropdownItem onSelect={saveImage}>
            <span>Saved image only</span>
            <span className="text-xs text-muted">As shown</span>
          </DropdownItem>
        )}
      </DropdownContent>
    </Dropdown>
  );
}
