import type { NextRequest } from "next/server";
import { getAuth } from "@/lib/auth/config";
import { authEnabled } from "@/lib/auth/enabled";

const off = () => new Response("Sign-in is off", { status: 404 });

export async function GET(req: NextRequest) {
  if (authEnabled()) return getAuth().handlers.GET(req);
  // The account button asks for the session on every page; answer "off" without an error status.
  if (req.nextUrl.pathname.endsWith("/auth/session")) return Response.json({ enabled: false });
  return off();
}
export async function POST(req: NextRequest) {
  return authEnabled() ? getAuth().handlers.POST(req) : off();
}
