"use client";
import { useEffect, useState } from "react";
import AddArea from "./AddArea";
import { AreaRow, TIER_LABEL } from "./AreaSearch";
import { selectCls } from "./styles";
import { ErrorNote, MockFlag } from "./ui";
import { errorMessage, isMock } from "@/lib/api";
import { getAreas } from "@/lib/night-api";
import type { AreasResponse, Tier } from "@/lib/night-types";

/** Every area we cover, by tier, plus "Add this area". */
export default function AreasBrowser() {
  const [tier, setTier] = useState<"" | Tier>("");
  const [data, setData] = useState<AreasResponse | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let off = false;
    getAreas({ tier: tier || undefined, limit: 100 })
      .then((r) => { if (!off) { setData(r); setErr(""); } })
      .catch((e) => { if (!off) setErr(errorMessage(e)); });
    return () => { off = true; };
  }, [tier]);

  // The fixture ignores ?tier=, so filter again here; the live API has already done it.
  const rows = data?.areas.filter((a) => !tier || a.tier === tier) ?? [];
  return (
    <div className="space-y-4">
      <AddArea />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">Covered areas{data ? ` (${rows.length})` : ""}</h2>
        <select aria-label="Coverage level" className={selectCls} value={tier} onChange={(e) => setTier(e.target.value as "" | Tier)}>
          <option value="">All areas</option>
          {(Object.keys(TIER_LABEL) as Tier[]).map((t) => <option key={t} value={t}>{TIER_LABEL[t]}{data?.counts_by_tier[t] != null ? ` (${data.counts_by_tier[t]})` : ""}</option>)}
        </select>
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      {!data && !err && <div className="skeleton h-40" />}
      {data && (
        <>
          <MockFlag on={isMock(data)} />
          <ul className="divide-y divide-line overflow-hidden rounded-xl bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.12)]">
            {rows.map((a) => <li key={`${a.geo_type}-${a.geo_id}`}><AreaRow a={a} /></li>)}
          </ul>
        </>
      )}
    </div>
  );
}
