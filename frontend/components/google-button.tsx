"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import { authApi } from "@/lib/api/data";

// The parts of Google Identity Services (https://accounts.google.com/gsi/client) this page uses.
type GoogleId = {
  initialize: (o: { client_id: string; callback: (r: { credential: string }) => void; ux_mode?: "popup" }) => void;
  renderButton: (el: HTMLElement, o: Record<string, string | number>) => void;
};
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

/**
 * "Continue with Google". The client id comes from the backend (GOOGLE_CLIENT_ID in backend/.env), so it is set
 * in one place; without it nothing is shown. onCredential gets Google's ID token, which the backend checks.
 */
export function GoogleButton({ onCredential, text = "continue_with" }: { onCredential: (credential: string) => void; text?: "continue_with" | "signup_with" | "signin_with" }) {
  const ref = useRef<HTMLDivElement>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const callback = useRef(onCredential);
  callback.current = onCredential;

  useEffect(() => {
    authApi
      .googleConfig()
      .then((c) => setClientId(c.enabled ? c.client_id : null))
      .catch(() => setClientId(null));
    if (window.google) setLoaded(true);
  }, []);

  useEffect(() => {
    if (!clientId || !loaded || !ref.current || !window.google) return;
    window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => callback.current(r.credential), ux_mode: "popup" });
    window.google.accounts.id.renderButton(ref.current, { theme: "outline", size: "large", shape: "rectangular", text, width: ref.current.offsetWidth || 320 });
  }, [clientId, loaded, text]);

  if (!clientId) return null;
  return (
    <>
      <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onLoad={() => setLoaded(true)} />
      <div ref={ref} className="flex min-h-10 w-full justify-center" />
      <div className="my-3 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
      </div>
    </>
  );
}
