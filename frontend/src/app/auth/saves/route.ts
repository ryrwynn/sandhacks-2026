import { type NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import { authEnabled } from "@/lib/auth/enabled";
import { subjectHash } from "@/lib/auth/hash";

/**
 * Browser-facing proxy for the signed-in user's saves (not under /api: Caddy sends /api/* to FastAPI).
 * It reads the Google subject from the session cookie, hashes it, and calls the API with the shared token.
 * The browser never sees the subject, the hash or the token.
 */
const API = () => process.env.API_INTERNAL_URL || "http://localhost:8000";
const json = (body: unknown, status: number) => NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } });

async function subject(req: NextRequest): Promise<string | null> {
  const secret = process.env.AUTH_SECRET;
  if (!secret) return null;
  // Auth.js names the session cookie (and salts the JWT with that name) by whether the site is served over https.
  const https = req.nextUrl.protocol === "https:" || req.headers.get("x-forwarded-proto") === "https";
  for (const secureCookie of https ? [true, false] : [false, true]) {
    try {
      const t = await getToken({
        req, secret, secureCookie,
        salt: secureCookie ? "__Secure-authjs.session-token" : "authjs.session-token",
      });
      if (t?.sub) return t.sub;
    } catch { /* try the other cookie name */ }
  }
  return null;
}

async function relay(req: NextRequest, method: "GET" | "PUT") {
  const token = process.env.ACCOUNT_API_TOKEN;
  if (!authEnabled() || !token) return json({ error: "off" }, 404);
  const sub = await subject(req);
  if (!sub) return json({ error: "signed out" }, 401);
  try {
    const res = await fetch(`${API()}/account/saves`, {
      method,
      headers: { "X-Account-Token": token, "X-Subject-Hash": subjectHash(sub), "Content-Type": "application/json" },
      body: method === "PUT" ? await req.text() : undefined,
      cache: "no-store",
    });
    return json(await res.json().catch(() => ({})), res.status);
  } catch {
    return json({ error: "unavailable" }, 503);
  }
}

export const GET = (req: NextRequest) => relay(req, "GET");
export const PUT = (req: NextRequest) => relay(req, "PUT");
