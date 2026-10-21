// Talks to the Python API in ../backend/api.py.
// Set NEXT_PUBLIC_API_URL in .env.local (local) or in Vercel (live site).
// The paid "Make border perfect" call does NOT go to the backend directly: it goes through this
// website's own server route (src/app/api/perfect/route.ts), which adds the secret API_TOKEN.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// Same fields as SettingsIn in backend/api.py (and CleanSettings / EvenSettings / OutputSettings).
export type Settings = {
  output: "bw" | "scan";
  method: "ai" | "classic";
  keep_detail: boolean;
  remove_shading: boolean;
  contrast: number;
  sharpness: number;
  thickness: number;
  even_width: "uniform" | "light" | "full" | "off";
  uniform_width: number;
  beautify: number;
  smooth: number;
  join_gaps: boolean;
  color: string;
  dpi: number;
  width_cm: number;
};

// Paid "Make border perfect" calls used for this photo, and the limit per photo.
export type PerfectUsage = { used: number; limit: number };

export type Result = {
  id: string;
  name: string;
  previews: { scan: string; clean: string; final: string; check: string | null };
  info: {
    output: "bw" | "scan";
    width: number;
    height: number;
    lines_from: "ai" | "classic" | null;
    closed_boxes: number | null;
    gaps_joined: number | null;
    loose_ends: number | null;
    ai_note: string | null;
    seconds: Record<string, number>;
  };
  formats: string[];
  perfect?: PerfectUsage;
  chat?: PerfectUsage; // chat messages used for this photo
};

export type Health = { ok: boolean; ai: boolean; ai_status: string; perfect?: boolean };

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

// Plain names for the settings, used when the server rejects a value.
const FIELD_NAMES: Record<string, string> = {
  output: "Output",
  method: "Line finder",
  contrast: "Contrast",
  sharpness: "Sharpness",
  thickness: "Line thickness",
  even_width: "Line width",
  uniform_width: "Pen width",
  beautify: "Beautify lines",
  smooth: "Smooth and straighten",
  color: "Line colour",
  dpi: "DPI",
  width_cm: "Width in cm",
  colors: "Number of colours",
  merge: "Merged colours",
  hidden: "Hidden layers",
};

type ValidationItem = { loc?: (string | number)[]; msg?: string };

/** Turns the server's error body into one sentence a user can understand. */
function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI / pydantic validation errors: [{loc: ["body", "dpi"], msg: "..."}]
    const parts = (detail as ValidationItem[]).map((d) => {
      const field = String(d.loc?.[d.loc.length - 1] ?? "");
      const name = FIELD_NAMES[field] ?? "A setting";
      const msg = (d.msg ?? "is not allowed").replace(/^Input should be /, "should be ").replace(/^Value error, /, "");
      return `${name} ${msg}`;
    });
    return `This setting is not allowed: ${parts.join("; ")}.`;
  }
  if (status === 429) return "This was used too often. Please wait a little and try again.";
  if (status >= 500) return "The server had a problem. Please try again in a moment.";
  return "Something went wrong. Please try again.";
}

async function readError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {}
  return new ApiError(errorMessage(body, res.status), res.status);
}

async function call<T>(url: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError("Could not reach the server. Please check your internet and try again.", 0);
  }
  if (!res.ok) throw await readError(res);
  return res.json();
}

export async function getHealth(): Promise<Health | null> {
  try {
    const res = await fetch(API_URL + "/api/health", { cache: "no-store" });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export function createSession(file: File, settings: Settings, autoCrop: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("auto_crop", String(autoCrop));
  form.append("settings", JSON.stringify(settings));
  return call<Result>(`${API_URL}/api/sessions`, { method: "POST", body: form });
}

export function updateSession(id: string, settings: Settings) {
  return call<Result>(`${API_URL}/api/sessions/${id}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

// "Make border perfect": the AI redraws the scanned image as clean line art; returns the image as a data URL.
// Goes through this website's server route, never to the backend directly (the token stays secret).
export function makePerfect(id: string) {
  const q = new URLSearchParams({ sid: id });
  return call<{ image: string; perfect: PerfectUsage }>(`/api/perfect?${q}`, { method: "POST" });
}

// "Chat to improve it": the user asks for a change in words. The server only accepts requests to improve
// or edit the border image; anything else comes back as a fixed refusal with no image.
export type ChatAnswer = { reply: string; image: string | null; perfect: PerfectUsage; chat: PerfectUsage };

export function sendChat(id: string, message: string) {
  const q = new URLSearchParams({ sid: id });
  return call<ChatAnswer>(`/api/chat?${q}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

// Colour layers: one layer per colour of the photo (free, made on the server without AI).
export type Layer = { id: number; hex: string; name: string; share: number };
export type LayersAnswer = { image: string; palette: Layer[] };
export type LayerOptions = {
  colors: number; // 0 = find the number automatically
  merge: [number, number][]; // [from layer id, to layer id]
  hidden: number[]; // layers left out of the preview
  show_lines: boolean;
};
export const DEFAULT_LAYER_OPTIONS: LayerOptions = { colors: 0, merge: [], hidden: [], show_lines: true };

export function getLayers(id: string, options: LayerOptions) {
  return call<LayersAnswer>(`${API_URL}/api/sessions/${id}/layers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
}

function fileNameFrom(res: Response, fallback: string) {
  const cd = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1] : fallback;
}

/**
 * Downloads one file (or the ZIP) and saves it. Errors such as "That size is too large"
 * are thrown as ApiError so the page can show them, instead of opening a raw error page.
 */
export async function downloadFile(id: string, fmt: string, fallbackName: string) {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/sessions/${id}/download?fmt=${encodeURIComponent(fmt)}`);
  } catch {
    throw new ApiError("Could not reach the server. Please check your internet and try again.", 0);
  }
  if (!res.ok) throw await readError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileNameFrom(res, fallbackName);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
