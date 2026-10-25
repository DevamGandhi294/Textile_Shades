"use client";

// Keeps one backend image session (backend/api.py) per design. The backend holds a photo in
// memory for an hour; when it has expired (404) the raw image is uploaded again and the call retried.

import { useCallback, useEffect, useRef, useState } from "react";
import { designsApi } from "@/lib/api/data";
import { isExpired, outlineApi, type OutlineSettings, type SessionResult } from "@/lib/api/outline";
import type { Design } from "@/lib/api/types";
import { urlToUploadFile } from "@/lib/image";

export function useOutlineSession(design: Design | undefined, settings: OutlineSettings) {
  const [sid, setSid] = useState<string | null>(null);
  const [result, setResult] = useState<SessionResult | null>(null);
  const [checked, setChecked] = useState(false);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  useEffect(() => {
    if (!design) return;
    let live = true;
    designsApi.getSession(design.id).then((s) => {
      if (!live) return;
      setSid(s);
      setChecked(true);
    });
    return () => {
      live = false;
    };
  }, [design?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const remember = useCallback(
    async (r: SessionResult) => {
      setSid(r.id);
      setResult(r);
      if (design) await designsApi.setSession(design.id, r.id);
      return r;
    },
    [design],
  );

  /** Upload a new photo for this design. */
  const upload = useCallback(
    async (file: File) => remember(await outlineApi.upload(file, settingsRef.current)),
    [remember],
  );

  /** Make sure the backend has this design's raw image; uploads the saved copy if needed. */
  const ensure = useCallback(async (): Promise<string> => {
    if (sid) return sid;
    const raw = design?.versions.find((v) => v.kind === "raw");
    if (!raw?.image_url) throw new Error("Upload a raw image first.");
    const r = await remember(await outlineApi.upload(await urlToUploadFile(raw.image_url, design!.name), settingsRef.current));
    return r.id;
  }, [sid, design, remember]);

  /** Runs fn with a live session id; on "expired" uploads the raw image again and retries once. */
  const withSession = useCallback(
    async <T,>(fn: (sid: string) => Promise<T>): Promise<T> => {
      const id = await ensure();
      try {
        return await fn(id);
      } catch (e) {
        if (!isExpired(e)) throw e;
        setSid(null);
        const raw = design?.versions.find((v) => v.kind === "raw");
        if (!raw) throw e;
        const r = await remember(await outlineApi.upload(await urlToUploadFile(raw.image_url, design!.name), settingsRef.current));
        return fn(r.id);
      }
    },
    [ensure, design, remember],
  );

  const update = useCallback(
    (s: OutlineSettings) => withSession(async (id) => remember(await outlineApi.update(id, s))),
    [withSession, remember],
  );

  return { sid, result, setResult, checked, upload, ensure, withSession, update };
}
