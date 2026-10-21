// Server-side gateway for the paid "Chat to improve it" call.
//
// The browser calls POST /api/chat?sid=<id> with {"message": "..."} on THIS website. This route
// checks the request, then forwards it to the Python backend and adds the secret API_TOKEN, which
// never reaches the browser. The backend checks that the message is a request to edit the border
// image (anything else gets a fixed refusal), and limits messages per photo and per hour.
import { SID, fail, forwardToBackend, sameOrigin } from "@/lib/gateway";
import { LIMITS } from "@/lib/settings";

// Runs on the Node.js server (the default runtime).
export const maxDuration = 300; // an allowed edit calls the image model, which can take up to 5 minutes

export async function POST(request: Request) {
  if (!sameOrigin(request)) return fail(403, "Not allowed.");

  const sid = new URL(request.url).searchParams.get("sid") ?? "";
  if (!SID.test(sid)) return fail(400, "This request is not valid. Please reload the page.");

  // read a small body only (a valid message is at most a few hundred characters)
  const raw = await request.text();
  if (raw.length > 4000) return fail(413, "That message is too long.");
  let message: unknown;
  try {
    message = (JSON.parse(raw) as { message?: unknown }).message;
  } catch {
    return fail(400, "This request is not valid. Please reload the page.");
  }
  if (typeof message !== "string" || !message.trim()) return fail(422, "Please type a message.");
  if (message.length > LIMITS.chatMaxChars) {
    return fail(422, `Please keep your message under ${LIMITS.chatMaxChars} characters.`);
  }

  return forwardToBackend(`/api/sessions/${sid}/chat`, "Chat", { message });
}
