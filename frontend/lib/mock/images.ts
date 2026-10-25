// Small SVG drawings for demo mode, so cards and the linked-image chain look real
// without shipping image files. "raw" looks like pencil on a phone photo; "outline" is clean.

export type Motif = "paisley" | "peacock" | "mango" | "temple" | "lotus" | "floral";

const MOTIF_PATH: Record<Motif, string> = {
  paisley:
    "M50 82c-18 0-28-14-26-30 2-17 18-30 34-26 13 3 18 16 12 26-5 8-15 9-20 3-4-5-1-12 5-12M50 82c10-2 22-10 24-24",
  peacock:
    "M50 85V48M50 48c-14-6-22-18-20-32 10 6 16 16 20 32zM50 48c14-6 22-18 20-32-10 6-16 16-20 32zM50 48c0-14 4-26 0-36-4 10 0 22 0 36zM42 60c-6 0-10 6-6 10M58 60c6 0 10 6 6 10",
  mango:
    "M38 84c-14-10-16-32-2-46 12-12 30-12 34 0 4 12-6 18-14 14M44 74c-6-6-6-16 2-22M56 30c4-6 10-8 16-6",
  temple:
    "M20 84h60M26 84V54h48v30M30 54l20-30 20 30M44 84V66h12v18M50 24v-8M38 54v-6h24v6",
  lotus:
    "M50 80c-10-10-12-28 0-44 12 16 10 34 0 44zM50 80c-18-2-30-14-32-30 14 0 26 10 32 30zM50 80c18-2 30-14 32-30-14 0-26 10-32 30zM30 84h40",
  floral:
    "M50 50m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0M50 42c-6-12 0-22 0-22s6 10 0 22M58 50c12-6 22 0 22 0s-10 6-22 0M50 58c6 12 0 22 0 22s-6-10 0-22M42 50c-12 6-22 0-22 0s10-6 22 0",
};

function svg(body: string, w: number, h: number, bg: string) {
  return (
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w * 4}" height="${h * 4}">` +
        `<rect width="100%" height="100%" fill="${bg}"/>${body}</svg>`,
    )
  );
}

function repeat(motif: Motif, cols: number, w: number, h: number, stroke: string, width: number, jitter: number) {
  const cell = w / cols;
  const scale = Math.min(cell, h - 16) / 100;
  let out = "";
  for (let i = 0; i < cols; i++) {
    const dx = i * cell + (cell - 100 * scale) / 2 + (jitter ? Math.sin(i * 2.1) * jitter : 0);
    const dy = 8 + (h - 16 - 100 * scale) / 2 + (jitter ? Math.cos(i * 1.7) * jitter : 0);
    const rot = jitter ? Math.sin(i) * jitter : 0;
    out += `<g transform="translate(${dx} ${dy}) scale(${scale}) rotate(${rot} 50 50)"><path d="${MOTIF_PATH[motif]}" fill="none" stroke="${stroke}" stroke-width="${width / scale}" stroke-linecap="round" stroke-linejoin="round"/></g>`;
  }
  return out;
}

export function demoImage(motif: Motif, kind: "raw" | "scan" | "ai" | "outline", cols = 3): string {
  const w = 120 * cols;
  const h = 130;
  const frame = (stroke: string, sw: number, off = 0) =>
    `<rect x="${4 + off}" y="${4 + off}" width="${w - 8}" height="${h - 8}" fill="none" stroke="${stroke}" stroke-width="${sw}"/>` +
    `<line x1="4" y1="${h - 14 + off}" x2="${w - 4}" y2="${h - 14 + off}" stroke="${stroke}" stroke-width="${sw}"/>`;

  if (kind === "raw") {
    // pencil on paper under a lamp: warm paper, soft grey, wobbly lines, a shadow corner
    const shadow = `<defs><radialGradient id="s" cx="0.9" cy="0.1" r="1"><stop offset="0" stop-color="#d9d2c3" stop-opacity="0"/><stop offset="1" stop-color="#8a8170" stop-opacity="0.45"/></radialGradient></defs><rect width="100%" height="100%" fill="url(#s)"/>`;
    return svg(shadow + frame("#6b665d", 1.2, 1) + repeat(motif, cols, w, h - 10, "#5f5a52", 1.4, 3), w, h, "#ece6d8");
  }
  if (kind === "scan") {
    return svg(frame("#3c3c3c", 1.2) + repeat(motif, cols, w, h - 10, "#3a3a3a", 1.3, 1.5), w, h, "#fbfbfb");
  }
  const sw = kind === "ai" ? 1.8 : 1.5;
  return svg(frame("#000", sw) + repeat(motif, cols, w, h - 10, "#000", sw, 0), w, h, "#fff");
}
