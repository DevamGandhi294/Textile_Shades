// Server-side gateway for the paid "Make border perfect" call.
//
// The browser calls POST /api/perfect?sid=<id> on THIS website. This route checks the request,
// then forwards it to the Python backend and adds the secret API_TOKEN, which never reaches the
// browser. The backend refuses the call without the token (when API_TOKEN is set there), and
// also limits calls per photo and per hour. See src/lib/gateway.ts.
import { SID, fail, forwardToBackend, sameOrigin } from "@/lib/gateway";

// Runs on the Node.js server (the default runtime).
export const maxDuration = 300; // the AI call can take up to 5 minutes

export async function POST(request: Request) {
  if (!sameOrigin(request)) return fail(403, "Not allowed.");

  const sid = new URL(request.url).searchParams.get("sid") ?? "";
  if (!SID.test(sid)) return fail(400, "This request is not valid. Please reload the page.");

  return forwardToBackend(`/api/sessions/${sid}/perfect`, "Make border perfect");
}
