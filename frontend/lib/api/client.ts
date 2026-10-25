// One fetch wrapper for every backend call. Errors become ApiError with a plain message
// a designer can read (401 login, 402/429 credits or limits, 422 bad settings).

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS !== "0";

/** The Next.js proxy in app/api/backend forwards these to the FastAPI backend. */
export const API_BASE = "/api/backend";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FALLBACK: Record<number, string> = {
  401: "Please log in again.",
  402: "Not enough credits. Buy extra credits or wait for your plan to renew.",
  404: "Not found.",
  413: "The photo is too big (more than 20 MB).",
  415: "Please upload a photo (JPG or PNG).",
  422: "One of the settings is not valid.",
  429: "Limit reached. Please wait a little and try again.",
  502: "The AI service did not answer. No credits were used. Please try again.",
  503: "The server is not reachable right now.",
};

function detailToText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: [...], msg: "..."}]
    const parts = detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== "body").join(" ") : "";
        return [loc, d?.msg].filter(Boolean).join(": ");
      })
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  return null;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "No internet connection, or the server is down.");
  }
  if (!res.ok) {
    let msg: string | null = null;
    try {
      msg = detailToText((await res.json())?.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg ?? FALLBACK[res.status] ?? `Something went wrong (${res.status}).`);
  }
  return (await res.json()) as T;
}

export function jsonBody(body: unknown): RequestInit {
  return { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export function errorText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
