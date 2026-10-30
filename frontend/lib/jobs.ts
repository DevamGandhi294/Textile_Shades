"use client";

// Long jobs (upload, apply settings, generate, AI layers, downloads) are kept here, outside React, by a key
// ("<designId>" or "<designId>:ai"). So a job keeps running, and stays visible as running, when the user opens
// another page or tab of the app and comes back. Only leaving the website (reload, close) stops it: then the
// browser asks first.

import { useCallback, useSyncExternalStore } from "react";

export type Job = { key: string; what: string; title: string; href: string; started: number };

const LABELS: Record<string, string> = {
  upload: "Scanning the photo",
  apply: "Applying settings",
  generate: "Making the AI result",
  watermark: "Removing the watermark",
  "edit-flip": "Making the new version",
  "edit-size": "Making the new version",
  analyse: "Checking the design",
  make: "Making the AI layers",
  psd: "Preparing the PSD",
  svg: "Preparing the SVG",
};

export const jobLabel = (what: string) => LABELS[what] ?? "Working";

let jobs: Record<string, Job> = {};
const listeners = new Set<() => void>();

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function setJob(key: string, what: string | null, title: string, href: string) {
  const next = { ...jobs };
  if (what) next[key] = { key, what, title, href, started: jobs[key]?.started ?? Date.now() };
  else delete next[key];
  jobs = next;
  listeners.forEach((fn) => fn());
}

/** Every running job. */
export function useJobs(): Record<string, Job> {
  return useSyncExternalStore(subscribe, () => jobs, () => jobs);
}

/** Like useState for "what is busy", but kept for the whole app: [what is running for `key`, set it]. */
export function useBusy(key: string, title: string, href: string): [string | null, (what: string | null) => void] {
  const all = useJobs();
  const set = useCallback((what: string | null) => setJob(key, what, title, href), [key, title, href]);
  return [all[key]?.what ?? null, set];
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", (e) => {
    if (Object.keys(jobs).length === 0) return;
    e.preventDefault(); // "Leave site? A job is still running" (it would stop)
    e.returnValue = "";
  });
}
