// Forwards /api/backend/* to the FastAPI backend (/api/*).
// The browser never sees BACKEND_URL or BACKEND_API_TOKEN, and no CORS setup is needed.

import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300; // the paid image call can take a minute or more

const BACKEND = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN = process.env.BACKEND_API_TOKEN;
const PASS_BACK = ["content-type", "content-disposition", "content-length"];

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path.some((p) => p === ".." || p.includes("/"))) {
    return Response.json({ detail: "Bad path." }, { status: 400 });
  }
  const url = `${BACKEND}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  for (const h of ["content-type", "cookie", "x-session-token"]) {
    const v = req.headers.get(h); // cookie = the login (mo_session, httpOnly), set by the backend
    if (v) headers.set(h, v);
  }
  if (TOKEN) headers.set("authorization", `Bearer ${TOKEN}`);

  let res: Response;
  try {
    res = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    // never show the server address to the user
    return Response.json(
      { detail: "The outline server is not reachable. Is backend/api.py running?" },
      { status: 503 },
    );
  }

  const out = new Headers();
  for (const h of PASS_BACK) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  for (const c of res.headers.getSetCookie()) out.append("set-cookie", c); // login and logout
  return new Response(res.body, { status: res.status, headers: out });
}

export { forward as GET, forward as POST, forward as PATCH, forward as PUT, forward as DELETE };
