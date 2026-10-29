// The real image engine: backend/api.py (sketchclean pipeline + OpenAI). These calls are live.
//
//   POST /api/sessions                  upload a photo  -> id + previews
//   POST /api/sessions/{id}/update      new settings    -> previews
//   POST /api/sessions/{id}/perfect     ?source=sketch|color  -> AI redraw (paid, limited)
//   POST /api/sessions/{id}/chat        {message}  -> ask for a change in words
//   POST /api/sessions/{id}/layers      {colors, merge, hidden, show_lines} -> colour layers
//   POST /api/sessions/{id}/ai-analyse  {machine}  -> AI layers step 1: the plan (cheap)
//   POST /api/sessions/{id}/ai-layers   -> one AI picture per layer of the plan (paid)
//   GET  /api/sessions/{id}/ai-layers   ?hidden=0,2  -> the AI layers and a preview (free)
//   POST /api/sessions/{id}/ai-layers/save  {version_id}  -> keep every layer with a saved design version
//   GET  /api/versions/{id}/layers.psd  -> the PSD of a saved version's layers (any time later)
//   POST /api/versions/{id}/transform   {flip_h, flip_v, mirror_half, width_cm, height_cm, fill, dpi} -> picture (free)
//   POST /api/versions/{id}/remove-watermark  -> picture without watermarks or text (paid)
//   GET  /api/sessions/{id}/download    ?fmt=...
//   GET  /api/health

import { ApiError, API_BASE, jsonBody, request } from "./client";
import type { ExportFormat } from "./types";

/** Same fields, defaults and limits as SettingsIn in backend/api.py. */
export interface OutlineSettings {
  output: "bw" | "scan";
  method: "ai" | "classic";
  keep_detail: boolean;
  remove_shading: boolean;
  contrast: number; // -1 .. 1
  sharpness: number; // 0 .. 2
  thickness: number; // -2 .. 3 (px of the original photo)
  even_width: "off" | "light" | "full" | "uniform";
  uniform_width: number; // 0 .. 100 (0 = automatic)
  beautify: number; // 0 .. 2
  smooth: number; // 0 .. 2
  join_gaps: boolean;
  color: string; // #000000
  dpi: number; // 72 .. 1200
  width_cm: number; // 0 .. 300 (0 = keep working size)
}

export const DEFAULT_SETTINGS: OutlineSettings = {
  output: "bw",
  method: "ai",
  keep_detail: true,
  remove_shading: true,
  contrast: 0,
  sharpness: 0.6,
  thickness: 0,
  even_width: "uniform",
  uniform_width: 0,
  beautify: 1,
  smooth: 1,
  join_gaps: true,
  color: "#000000",
  dpi: 300,
  width_cm: 0,
};

export interface Usage {
  used: number;
  limit: number;
}

export interface SessionResult {
  id: string;
  name: string;
  previews: { scan: string | null; clean: string | null; final: string | null; check: string | null };
  info: {
    output: "bw" | "scan";
    width: number;
    height: number;
    lines_from: string | null;
    closed_boxes: number | null;
    gaps_joined: number | null;
    loose_ends: number | null;
    ai_note: string | null;
    seconds: Record<string, number> | null;
  };
  formats: string[];
  perfect: Usage;
  chat: Usage;
}

export interface Health {
  ok: boolean;
  ai: boolean;
  ai_status: string;
  perfect: boolean;
}

export interface PerfectResult {
  image: string;
  perfect: Usage;
}

export interface ChatResult {
  reply: string;
  image: string | null;
  perfect: Usage;
  chat: Usage;
}

export interface LayerColour {
  id: number;
  hex: string;
  name: string;
  share: number;
}

export interface LayersResult {
  image: string;
  palette: LayerColour[];
}

export interface LayersInput {
  colors: number; // 0 = automatic, else 2..12
  merge: [number, number][]; // (from, to)
  hidden: number[];
  show_lines: boolean;
}

/** What the AI layers are for; it changes how the AI splits the design. */
export type Machine = "embroidery" | "print" | "cad";

export interface AiPlan {
  image_type: "line" | "color";
  is_complete: boolean;
  is_symmetric: boolean;
  mirror: boolean; // the left half is drawn and mirrored
  background_color: string; // one solid layer at the bottom (no AI call)
  layers: { name: string; description: string; border_color: string }[]; // outlines only, in border_color
  machine: Machine;
  model: string; // the image model chosen for this design
}

export interface AiLayersState {
  plan: AiPlan | null;
  runs: Usage; // how many times the layers were made for this photo
  made: boolean;
  image?: string; // preview of the layers stacked
  layers?: { id: number; name: string }[];
}

/** Free edits of a saved result (Python, no AI). Same fields as TransformIn in backend/api.py. */
export interface TransformInput {
  flip_h?: boolean;
  flip_v?: boolean;
  mirror_half?: boolean;
  width_cm?: number; // 0 = keep
  height_cm?: number; // 0 = keep the shape
  fill?: "repeat" | "stretch" | "fit"; // how a new shape is filled when both sizes are given
  dpi?: number;
}

export interface EditedPicture {
  image: string; // data URL (PNG)
  width_px: number;
  height_px: number;
  dpi?: number | null;
  model?: string;
}

export const MAX_CHAT_CHARS = 300;

export const outlineApi = {
  health: () => request<Health>(`${API_BASE}/health`),

  upload(file: File, settings: OutlineSettings, autoCrop = true) {
    const form = new FormData();
    form.append("file", file);
    form.append("auto_crop", String(autoCrop));
    form.append("settings", JSON.stringify(settings));
    return request<SessionResult>(`${API_BASE}/sessions`, { method: "POST", body: form });
  },

  update: (sid: string, settings: OutlineSettings) =>
    request<SessionResult>(`${API_BASE}/sessions/${sid}/update`, jsonBody(settings)),

  perfect: (sid: string, source: "sketch" | "color" = "sketch") =>
    request<PerfectResult>(`${API_BASE}/sessions/${sid}/perfect?source=${source}`, { method: "POST" }),

  chat: (sid: string, message: string) =>
    request<ChatResult>(`${API_BASE}/sessions/${sid}/chat`, jsonBody({ message })),

  layers: (sid: string, body: LayersInput) =>
    request<LayersResult>(`${API_BASE}/sessions/${sid}/layers`, jsonBody(body)),

  aiAnalyse: (sid: string, machine: Machine) =>
    request<AiLayersState>(`${API_BASE}/sessions/${sid}/ai-analyse`, jsonBody({ machine })),

  aiMake: (sid: string) => request<AiLayersState>(`${API_BASE}/sessions/${sid}/ai-layers`, { method: "POST" }),

  aiLayers: (sid: string, hidden: number[] = []) =>
    request<AiLayersState>(`${API_BASE}/sessions/${sid}/ai-layers?hidden=${hidden.join(",")}`),

  /** Keep every AI layer with a saved design version, so its PSD can be made again after the session ends. */
  aiSave: (sid: string, versionId: string) =>
    request<{ ok: boolean; layers: number }>(`${API_BASE}/sessions/${sid}/ai-layers/save`, jsonBody({ version_id: versionId })),

  /** Flip, mirror half, new size, fill by repeating: a new picture from a saved result (free). */
  transform: (versionId: string, body: TransformInput) =>
    request<EditedPicture>(`${API_BASE}/versions/${versionId}/transform`, jsonBody(body)),

  /** The AI removes watermarks and text from a saved result, nothing else (paid). */
  removeWatermark: (versionId: string) =>
    request<EditedPicture>(`${API_BASE}/versions/${versionId}/remove-watermark`, { method: "POST" }),

  /** The PSD of a saved version's layers (no image session needed). */
  savedLayersPsd: (versionId: string) => saveFile(`${API_BASE}/versions/${versionId}/layers.psd`, "ai_layers.psd"),

  downloadUrl: (sid: string, fmt: ExportFormat) =>
    `${API_BASE}/sessions/${sid}/download?fmt=${encodeURIComponent(fmt)}`,

  /** Fetches the file and saves it with the name the server gives. */
  download(sid: string, fmt: ExportFormat) {
    return saveFile(this.downloadUrl(sid, fmt), `outline.${fmt}`);
  },
};

/** Fetches a file from the backend and saves it with the name the server gives. */
async function saveFile(path: string, fallbackName: string) {
  const res = await fetch(path);
  if (!res.ok) {
    let msg = `Download failed (${res.status}).`;
    try {
      const d = (await res.json())?.detail;
      if (typeof d === "string") msg = d;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  const name = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = decodeURIComponent(name);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** The session lives in the backend's memory for an hour; 404 means upload again. */
export function isExpired(e: unknown) {
  return e instanceof ApiError && e.status === 404;
}
