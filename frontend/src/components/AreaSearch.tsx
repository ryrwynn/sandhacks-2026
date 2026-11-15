"use client";
import Link from "next/link";
import { useState } from "react";
import { Search } from "lucide-react";
import { errorMessage, isMock } from "@/lib/api";
import { getAreas } from "@/lib/night-api";
import type { AreaSummary } from "@/lib/night-types";
import { usd } from "@/lib/format";
import AddArea from "./AddArea";
import { btnCls, inputCls } from "./styles";
import { ErrorNote, MockFlag } from "./ui";

export const TIER_LABEL: Record<AreaSummary["tier"], string> = {
  core: "Full coverage", county: "County listings", index: "Prices and forecasts only", on_demand: "Added on request",
};

export function AreaRow({ a, onPick }: { a: AreaSummary; onPick?: (a: AreaSummary) => void }) {
  const inner = (
    <>
      <span className="min-w-0">
        <span className="block truncate font-medium">{a.geo_type === "zip" ? `${a.geo_id} ` : ""}{a.name}</span>
        <span className="block truncate text-xs text-muted">{TIER_LABEL[a.tier]}{a.county ? `, ${a.county} County` : ""}{!a.has_listings ? ", no listings yet" : ""}</span>
      </span>
      <span className="shrink-0 text-sm font-semibold tabular-nums">{a.typical_rent_usd != null ? `${usd(a.typical_rent_usd)}/mo` : ""}</span>
    </>
  );
  const cls = "flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-bg";
  if (onPick && a.centroid_lat != null) return <button type="button" className={cls} onClick={() => onPick(a)}>{inner}</button>;
  return a.geo_type === "zip" ? <Link href={`/zip/${a.geo_id}`} className={cls}>{inner}</Link> : <div className={cls}>{inner}</div>;
}

/** Search known areas by ZIP or city. With no match it offers "Add this area" prefilled with the search. */
export default function AreaSearch({ onPick }: { onPick?: (a: AreaSummary) => void }) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<AreaSummary[] | null>(null);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [mock, setMock] = useState(false);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    const t = q.trim();
    if (!t) return;
    setBusy(true);
    setErr("");
    try {
      const r = await getAreas({ q: t, limit: 6 });
      setMock(isMock(r));
      // Sample data is not a search result: with the fixture, filter it by the text so "no match" still shows.
      const list = isMock(r) ? r.areas.filter((a) => `${a.geo_id} ${a.name}`.toLowerCase().includes(t.toLowerCase())) : r.areas;
      setFound(list);
      setAsked(t);
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <MockFlag on={mock} />
      <form onSubmit={go} role="search" aria-label="Search areas" className="flex gap-2">
        <input className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a ZIP or city" aria-label="Search a ZIP or city" maxLength={80} />
        <button className={`${btnCls} shrink-0 gap-1.5`} disabled={busy}><Search size={18} aria-hidden="true" /> Search</button>
      </form>
      {err && <ErrorNote>{err}</ErrorNote>}
      {found && found.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-xl bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.12)]" aria-label="Matching areas">
          {found.map((a) => <li key={`${a.geo_type}-${a.geo_id}`}><AreaRow a={a} onPick={onPick} /></li>)}
        </ul>
      )}
      {found && found.length === 0 && (
        <>
          <p className="text-sm text-muted">No area called &quot;{asked}&quot; is loaded yet.</p>
          <AddArea compact initialQuery={asked} />
        </>
      )}
    </div>
  );
}
