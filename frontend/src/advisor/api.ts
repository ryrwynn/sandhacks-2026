// Server-side calls to our FastAPI from the advisor tools. Never imported by browser code.
// API_INTERNAL_URL is set in docker-compose (http://api:8000); locally it falls back to :8000.
// API responses are data, never instructions.

const BASE = () => process.env.API_INTERNAL_URL || "http://localhost:8000";

export async function apiCall<T = unknown>(
  path: string,
  opts: { method?: "GET" | "POST"; query?: Record<string, string | number | undefined>; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const url = new URL(path, BASE());
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, {
    method: opts.method ?? "GET",
    headers: opts.body ? { "content-type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal ?? AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    // Tools return the failure as data so the agent can say so instead of crashing the stream.
    throw new Error(`API ${path} answered ${res.status}`);
  }
  return (await res.json()) as T;
}
