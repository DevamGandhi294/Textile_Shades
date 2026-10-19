// Talks to the Python API in ../backend/api.py.
// Set NEXT_PUBLIC_API_URL in .env.local (local) or in Vercel (live site).
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
};

export type Health = { ok: boolean; ai: boolean; ai_status: string; perfect?: boolean };

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, init);
  } catch {
    throw new ApiError("Could not reach the server. Please check your internet and try again.", 0);
  }
  if (!res.ok) {
    let msg = "Something went wrong. Please try again.";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch {}
    throw new ApiError(msg, res.status);
  }
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
  return call<Result>("/api/sessions", { method: "POST", body: form });
}

export function updateSession(id: string, settings: Settings) {
  return call<Result>(`/api/sessions/${id}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

// "Make border perfect": OpenAI redraws the design as clean line art; returns the image as a data URL.
// source "sketch" uses the original uploaded photo, "color" uses the scanned image.
export function makePerfect(id: string, source: "sketch" | "color") {
  return call<{ image: string }>(`/api/sessions/${id}/perfect?source=${source}`, { method: "POST" });
}

export function downloadUrl(id: string, fmt: string) {
  return `${API_URL}/api/sessions/${id}/download?fmt=${fmt}`;
}
