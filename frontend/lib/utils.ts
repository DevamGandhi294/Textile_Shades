import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** "Today", "2 days", "12 Oct" — the short dates used in the lists. */
export function shortAgo(iso: string, now = new Date()): string {
  const d = new Date(iso);
  const days = Math.floor((startOfDay(now).getTime() - startOfDay(d).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days`;
  if (days < 14) return "1 week";
  if (days < 30) return `${Math.floor(days / 7)} weeks`;
  if (days < 60) return "1 month";
  return shortDate(iso);
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function startOfDay(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

export function uid(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function sizeLabel(wMm?: number | null, hMm?: number | null): string | null {
  if (!wMm || !hMm) return null;
  const cm = (v: number) => (Math.round(v / 1) / 10).toString();
  return `${cm(wMm)} × ${cm(hMm)} cm`;
}

export function dataUrlToFile(dataUrl: string, name: string): File {
  const [head, body] = dataUrl.split(",");
  const mime = /data:([^;]+)/.exec(head!)?.[1] ?? "image/png";
  const bin = atob(body!);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], name, { type: mime });
}

export function fileToDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
