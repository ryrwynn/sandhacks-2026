import type { NextRequest } from "next/server";
import { getAuth } from "@/lib/auth/config";
import { authEnabled } from "@/lib/auth/enabled";

const off = () => new Response("Sign-in is off", { status: 404 });

export async function GET(req: NextRequest) {
  return authEnabled() ? getAuth().handlers.GET(req) : off();
}
export async function POST(req: NextRequest) {
  return authEnabled() ? getAuth().handlers.POST(req) : off();
}
