import { NextRequest } from "next/server";
import { getAuth } from "@/lib/auth/config";
import { authEnabled } from "@/lib/auth/enabled";

const off = () => new Response("Sign-in is off", { status: 404 });

/**
 * The web container listens on 0.0.0.0:3000 behind Caddy, and Next builds req.url from that bind address, so
 * Auth.js sent Google a redirect_uri of http://0.0.0.0:3000/... (the sign-in landed on 0.0.0.0). Rebuild the URL
 * on the public origin: AUTH_URL when set, else the forwarded (or Host) header and scheme.
 */
function publicOrigin(req: Request): string | null {
  const env = process.env.AUTH_URL;
  if (env) {
    try { return new URL(env).origin; } catch { /* fall through to the headers */ }
  }
  const h = req.headers;
  const host = (h.get("x-forwarded-host") || h.get("host") || "").split(",")[0].trim();
  if (!host || /^(0\.0\.0\.0|\[::\])(:\d+)?$/.test(host)) return null;
  const local = /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host);
  const proto = (h.get("x-forwarded-proto") || "").split(",")[0].trim() || (local ? "http" : "https");
  return `${proto}://${host}`;
}

async function onPublicOrigin(req: NextRequest): Promise<NextRequest> {
  const origin = publicOrigin(req);
  if (!origin) return req;
  const u = new URL(req.url);
  const fixed = new URL(u.pathname + u.search, origin);
  if (fixed.href === u.href) return req;
  const hasBody = req.method !== "GET" && req.method !== "HEAD";   // Auth.js POSTs are small forms
  return new NextRequest(fixed, { method: req.method, headers: req.headers, body: hasBody ? await req.text() : undefined });
}

export async function GET(req: NextRequest) {
  if (authEnabled()) return getAuth().handlers.GET(await onPublicOrigin(req));
  // The account button asks for the session on every page; answer "off" without an error status.
  if (req.nextUrl.pathname.endsWith("/auth/session")) return Response.json({ enabled: false });
  return off();
}
export async function POST(req: NextRequest) {
  return authEnabled() ? getAuth().handlers.POST(await onPublicOrigin(req)) : off();
}
