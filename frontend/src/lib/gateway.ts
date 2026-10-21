// Server-side helpers for the routes that call the PAID backend endpoints
// (src/app/api/perfect and src/app/api/chat). Use only in route handlers, never in browser code.
//
// Server-only environment variables (never prefix them with NEXT_PUBLIC_):
//   API_TOKEN    same value as API_TOKEN in backend/.env
//   BACKEND_URL  backend address as seen from this server (default: NEXT_PUBLIC_API_URL)

export const SID = /^[0-9a-f]{32}$/; // session ids are uuid4().hex on the backend
const BACKEND_TIMEOUT_MS = 310_000; // a little longer than the backend's own 300 s OpenAI timeout

function backendUrl() {
  return (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function fail(status: number, detail: string) {
  return Response.json({ detail }, { status, headers: { "Cache-Control": "no-store" } });
}

/** Only pages of this website may use the routes (blocks other sites calling them from a browser). */
export function sameOrigin(request: Request) {
  const site = request.headers.get("sec-fetch-site");
  if (site) return site === "same-origin";
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).host === new URL(request.url).host;
  } catch {
    return false;
  }
}

/**
 * Calls the backend with the secret token and passes its answer through (data or its plain error message).
 * `what` names the feature in log lines and error messages.
 */
export async function forwardToBackend(path: string, what: string, json?: unknown) {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (json !== undefined) headers["Content-Type"] = "application/json";
  if (process.env.API_TOKEN) headers.Authorization = `Bearer ${process.env.API_TOKEN}`;

  let res: Response;
  try {
    res = await fetch(backendUrl() + path, {
      method: "POST",
      headers,
      body: json === undefined ? undefined : JSON.stringify(json),
      cache: "no-store",
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    });
  } catch (e) {
    const timedOut = e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError");
    return timedOut
      ? fail(504, `${what} took too long. Please try again later.`)
      : fail(502, "Could not reach the server. Please try again in a moment.");
  }

  if (res.status === 401) {
    // the token is wrong or missing: a setup problem, not something the user can fix
    console.error(`${what}: the backend refused the API token (check API_TOKEN on both servers).`);
    return fail(502, `${what} is not available right now.`);
  }

  const body = await res.text();
  return new Response(body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json", "Cache-Control": "no-store" },
  });
}
