"use client";
import { useEffect, useState } from "react";
import { mergeSaves, type RemoteSave } from "@/lib/auth/merge";
import type { SavedItem } from "@/lib/saved";

/**
 * Optional Google sign-in button. Renders nothing when sign-in is off (/auth/session answers {enabled: false}),
 * when the check fails, or until the check finishes, so the site looks exactly as it did without accounts.
 * While signed in it also keeps this browser's saves and the server copy in step (see lib/auth/merge.ts).
 * Local saving stays the source of truth: any failure here leaves localStorage untouched.
 */
type State = "unknown" | "off" | "out" | "in";

const SAVED_KEY = "rentorknot:saved:v1";        // owned by lib/saved.tsx
const SYNCED_KEY = "rentorknot:account:synced:v1"; // ids already known to the server

function readLocal(): { items: SavedItem[]; seeded: boolean } | null {
  try {
    const j = JSON.parse(localStorage.getItem(SAVED_KEY) ?? "null");
    return j && Array.isArray(j.items) ? { items: j.items, seeded: !!j.seeded } : { items: [], seeded: false };
  } catch { return null; }
}
function readSynced(): number[] {
  try { const j = JSON.parse(localStorage.getItem(SYNCED_KEY) ?? "[]"); return Array.isArray(j) ? j.filter((x) => typeof x === "number") : []; }
  catch { return []; }
}
function setSynced(ids: number[]) { try { localStorage.setItem(SYNCED_KEY, JSON.stringify(ids)); } catch { /* ignore */ } }

/** Merge once. `pull` also writes server-only saves into this browser (and reloads so the list shows them). */
async function sync(pull: boolean) {
  const local = readLocal();
  if (!local) return;
  const res = await fetch("/auth/saves", { cache: "no-store" });
  if (!res.ok) return;
  const remote = ((await res.json()) as { items?: RemoteSave[] }).items ?? [];
  const m = mergeSaves(local.items, remote, readSynced());
  if (m.changedRemote) {
    const put = await fetch("/auth/saves", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: m.remote, merge: false }),
    });
    if (!put.ok) return;
  }
  const localIds = new Set(local.items.map((i) => i.id));
  setSynced(pull ? m.remote.map((r) => r.listing_id) : m.remote.map((r) => r.listing_id).filter((id) => localIds.has(id)));
  if (pull && m.changedLocal) {
    try {
      localStorage.setItem(SAVED_KEY, JSON.stringify({ items: m.local, seeded: true }));
      location.reload();
    } catch { /* storage blocked: stay local */ }
  }
}

export function AccountButton({ className = "" }: { className?: string }) {
  const [state, setState] = useState<State>("unknown");

  useEffect(() => {
    let cancelled = false;
    fetch("/auth/session", { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) return "off" as const;                       // 404: older servers with sign-in off
        const s = await r.json().catch(() => null);
        if (s && typeof s === "object" && (s as { enabled?: boolean }).enabled === false) return "off" as const;
        return s && typeof s === "object" && "expires" in s ? ("in" as const) : ("out" as const);
      })
      .catch(() => "off" as const)
      .then((s) => { if (!cancelled) setState(s); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (state !== "in") return;
    const run = (pull: boolean) => { sync(pull).catch(() => {}); };
    run(true);
    const tick = setInterval(() => run(false), 8000);
    const vis = () => { if (document.visibilityState === "visible") run(true); };
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(tick); document.removeEventListener("visibilitychange", vis); };
  }, [state]);

  if (state === "off" || state === "unknown") return null;
  const base = `inline-flex min-h-11 items-center rounded-lg border border-line bg-surface px-3 text-sm font-medium text-ink hover:bg-slate-100 ${className}`;
  return (
    <span className="inline-flex items-center gap-2">
      {state === "in" ? (
        <a href="/auth/signout" className={base} title="Your saves are synced to your Google account (no email or name is kept)">Signed in · Sign out</a>
      ) : (
        <a href="/auth/signin" className={base} title="Optional: keep your saves on every device">Sign in</a>
      )}
      <a href="/privacy" className="inline-flex min-h-11 items-center text-xs text-muted underline"
        title="Sign-in stores only a hashed account ID, never your email or name">
        <span className="hidden xl:inline">Only a hashed ID is stored ·&nbsp;</span>Privacy
        <span className="sr-only xl:hidden"> (sign-in stores only a hashed account ID)</span>
      </a>
    </span>
  );
}

export default AccountButton;
