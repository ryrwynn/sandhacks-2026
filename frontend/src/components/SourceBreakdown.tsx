"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type * as C from "@/lib/api.generated";
import { getMarket } from "@/lib/api";
import { usd } from "@/lib/format";
import { cardCls } from "./styles";

const med = (s: C.SourceStat) => (s.median_usd != null ? `median ${usd(s.median_usd)}` : "no median yet");

/** Where the active listings come from, and a toggle that leaves Facebook groups out. */
export function SourceBreakdownView({ sources, sitesOnly, onToggle }: {
  sources: C.SourceBreakdown; sitesOnly: boolean; onToggle: (v: boolean) => void;
}) {
  const fbAny = sources.facebook.count + sources.facebook_rooms.count > 0;
  return (
    <div className="space-y-2 text-sm">
      <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
        <li><span className="font-semibold">Listing sites:</span> {sources.listing_sites.count.toLocaleString()} · {med(sources.listing_sites)}</li>
        {!sitesOnly && (
          <>
            <li>
              <span className="font-semibold">Facebook groups:</span> {sources.facebook.count.toLocaleString()} whole units · {med(sources.facebook)}
              <span className="text-muted"> (half weight)</span>
            </li>
            <li className="text-muted">Rooms and sublets: {sources.facebook_rooms.count.toLocaleString()} · {med(sources.facebook_rooms)} (not in unit medians)</li>
            {sources.facebook_unusual > 0 && <li className="text-muted">Unusual prices left out of medians: {sources.facebook_unusual}</li>}
          </>
        )}
      </ul>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 font-medium">
          <input type="checkbox" className="h-5 w-5 accent-[var(--primary)]" checked={sitesOnly} onChange={(e) => onToggle(e.target.checked)} />
          Listing sites only
        </label>
        {fbAny && !sitesOnly && (
          <Link href="/find?source=facebook" className="inline-flex min-h-11 items-center font-medium text-accent-strong underline underline-offset-2">See Facebook listings</Link>
        )}
      </div>
    </div>
  );
}

/** ZIP page: the market source breakdown for one ZIP, with its own toggle. */
export function ZipSourceCard({ zip }: { zip: string }) {
  const [sitesOnly, setSitesOnly] = useState(false);
  const [m, setM] = useState<C.MarketResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    getMarket({ zip, listingSitesOnly: sitesOnly }).then((x) => { if (!cancelled) setM(x); }).catch(() => {});
    return () => { cancelled = true; };
  }, [zip, sitesOnly]);
  return (
    <section aria-labelledby="src-h" className={`${cardCls} space-y-2 p-4 sm:p-6`}>
      <h2 id="src-h" className="text-xl font-bold">Where the listings come from</h2>
      {!m ? <div className="skeleton h-16" /> : (
        <>
          <p className="text-muted">{m.active_listings.toLocaleString()} active listings in {zip}{sitesOnly ? " on listing sites" : ""}.</p>
          <SourceBreakdownView sources={m.sources} sitesOnly={sitesOnly} onToggle={setSitesOnly} />
        </>
      )}
    </section>
  );
}
