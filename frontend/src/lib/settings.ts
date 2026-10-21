import type { Settings } from "./api";

// Recommended settings: the same defaults as backend/sketchclean/config.py.
export const DEFAULTS: Settings = {
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

export const isDefault = (s: Settings) => JSON.stringify(s) === JSON.stringify(DEFAULTS);

// Every file type the backend can make. `bwOnly` = needs "Clean lines".
export const FORMATS = [
  { fmt: "png", label: "Picture (PNG)", hint: "Phone, WhatsApp, auto-digitizing", bwOnly: false },
  { fmt: "pdf", label: "For printing (PDF)", hint: "Print or send by email", bwOnly: true },
  { fmt: "eps", label: "For Wilcom embroidery (EPS)", hint: "Wilcom E4 vectors", bwOnly: true },
  { fmt: "dxf", label: "For CAD / Wilcom (DXF)", hint: "Choose millimetres when opening", bwOnly: true },
  { fmt: "svg", label: "For CorelDRAW / Illustrator (SVG)", hint: "Also Inkscape", bwOnly: true },
  { fmt: "tiff", label: "High quality picture (TIFF)", hint: "For textile CAD", bwOnly: false },
  { fmt: "bmp", label: "Simple picture (BMP)", hint: "Wilcom auto-digitizing", bwOnly: false },
] as const;

export const ALL_FORMATS: string[] = FORMATS.map((f) => f.fmt);

// Same limits as SettingsIn and export.Page in backend/api.py and backend/sketchclean/export.py.
export const LIMITS = {
  widthCmMax: 300,
  dpiMin: 72,
  dpiMax: 1200,
  maxOutputPixels: 120_000_000,
  chatMaxChars: 300, // same as CHAT_MAX_CHARS in backend/api.py
};

/**
 * True when the downloaded files would be too large for the server
 * (the server refuses it with "That size is too large"). workW/workH: the working size of the photo.
 */
export function outputTooLarge(workW: number, workH: number, s: Settings) {
  const outW = s.width_cm > 0 ? Math.round((s.width_cm / 2.54) * s.dpi) : workW;
  const outH = Math.round(workH * (outW / workW));
  return outW * outH > LIMITS.maxOutputPixels;
}
