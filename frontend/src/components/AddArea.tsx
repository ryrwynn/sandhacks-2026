"use client";
import { useEffect, useRef, useState } from "react";
import { MapPinPlus } from "lucide-react";
import { errorMessage, isMock } from "@/lib/api";
import { getAreaRequest, requestArea } from "@/lib/night-api";
import type { AreaRequestStatus } from "@/lib/night-types";
import { btnCls, inputCls } from "./styles";
import { Card, ErrorNote, MockFlag } from "./ui";
import { usd } from "@/lib/format";

const DONE = new Set(["loaded", "failed", "over_budget"]);
const LABEL: Record<AreaRequestStatus["status"], string> = {
  queued: "Queued", scraping: "Loading listings", loaded: "Loaded", failed: "Failed", over_budget: "Over today's budget",
};

/** Status of one area request: estimate, place in the queue, and what happened. Polls while it is queued or running. */
export function AreaRequestCard({ req }: { req: AreaRequestStatus }) {
  return (
    <div className="space-y-2 rounded-lg bg-bg p-3 text-sm" role="status" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold">{req.name}</span>
        <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-semibold text-ink ring-1 ring-line">{LABEL[req.status]}</span>
      </div>
      <p>{req.message}</p>
      <dl className="grid grid-cols-2 gap-2 text-xs text-muted sm:grid-cols-4">
        <div><dt>Estimated records</dt><dd className="text-sm font-semibold tabular-nums text-ink">{req.est_records ?? "n/a"}</dd></div>
        <div><dt>Estimated cost</dt><dd className="text-sm font-semibold tabular-nums text-ink">{req.est_cost_usd != null ? usd(req.est_cost_usd, 2) : "n/a"}</dd></div>
        <div><dt>Queue position</dt><dd className="text-sm font-semibold tabular-nums text-ink">{req.queue_position ?? "none"}</dd></div>
        <div><dt>Budget left today</dt><dd className="text-sm font-semibold tabular-nums text-ink">{req.budget_remaining_usd != null ? usd(req.budget_remaining_usd, 2) : "n/a"}</dd></div>
      </dl>
    </div>
  );
}

/** "Add this area": ask for a California ZIP or city to be loaded. Shows the cost estimate and queue status. */
export default function AddArea({ initialQuery = "", compact = false }: { initialQuery?: string; compact?: boolean }) {
  const [query, setQuery] = useState(initialQuery);
  const [req, setReq] = useState<AreaRequestStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [mock, setMock] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const polls = useRef(0);

  useEffect(() => setQuery(initialQuery), [initialQuery]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  function poll(id: string) {
    timer.current = setTimeout(async () => {
      if (++polls.current > 60) return;
      try {
        const r = await getAreaRequest(id);
        setReq(r);
        setMock(isMock(r));
        if (!DONE.has(r.status) && !isMock(r)) poll(id);   // a sample answer never changes: stop asking
      } catch { /* keep the last status; the person can resubmit */ }
    }, 5000);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q.length < 2) return setErr("Enter a California ZIP code or city name.");
    setErr("");
    setBusy(true);
    polls.current = 0;
    if (timer.current) clearTimeout(timer.current);
    try {
      const r = await requestArea(q);
      setReq(r);
      setMock(isMock(r));
      if (!DONE.has(r.status) && !r.already_covered && !isMock(r)) poll(r.request_id);
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const body = (
    <form onSubmit={submit} className="space-y-3" aria-label="Add this area">
      <MockFlag on={mock} />
      <div className="flex items-center gap-2">
        <MapPinPlus size={20} aria-hidden="true" className="shrink-0 text-accent-strong" />
        <h2 className="text-base font-bold">Add this area</h2>
      </div>
      <p className="text-sm text-muted">Not on the map yet? Ask for a California ZIP or city. We show the cost estimate and your place in the queue; nothing is posted anywhere.</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          className={inputCls}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ZIP code or city, e.g. 95814"
          aria-label="ZIP code or city"
          maxLength={80}
        />
        <button className={`${btnCls} shrink-0`} disabled={busy}>{busy ? "Checking..." : "Add this area"}</button>
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      {req && <AreaRequestCard req={req} />}
    </form>
  );
  return compact ? <div className="rounded-xl bg-surface p-4 shadow-[0_1px_3px_rgba(46,49,39,0.12)]">{body}</div> : <Card>{body}</Card>;
}
