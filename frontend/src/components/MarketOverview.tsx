"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import ApartmentCard, { CardSkeletons } from "./ApartmentCard";
import FilterBar from "./FilterBar";
import RentChart from "./RentChart";
import { cardCls } from "./styles";
import { errorMessage, getHealth, getMarket } from "@/lib/api";
import { usd } from "@/lib/format";
import { useSaved } from "@/lib/saved";
import { DEFAULT_FILTERS, type Filters } from "@/lib/types";
import { fmtDate, fmtMonth, type MarketRange, type MarketResponse } from "@/lib/tracker";
import { ErrorNote } from "./ui";
import { SourceBreakdownView } from "./SourceBreakdown";

export default function MarketOverview({ map }: { map: ReactNode }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [range, setRange] = useState<MarketRange>("1y");
  const [sitesOnly, setSitesOnly] = useState(false);
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [scrape, setScrape] = useState<string | null>(null);
  const { items, listings, ready, loading: savedLoading, has, remove } = useSaved();

  useEffect(() => { getHealth().then((h) => setScrape(h.last_scrape_at)).catch(() => {}); }, []);
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    getMarket({ zip: filters.zip, beds: filters.beds, type: filters.type, range, listingSitesOnly: sitesOnly })
      .then((m) => { if (!cancelled) { setMarket(m); setErr(""); } })
      .catch((e) => { if (!cancelled) setErr(errorMessage(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filters.zip, filters.beds, filters.type, range, sitesOnly]);

  const updated = market?.updated_at ?? scrape;
  const last = market?.points[market.points.length - 1];
  const label = !last ? "Rent" : last.basis === "zori" ? "Typical rent (Zillow index)" : "Median asking rent";
  const c = market?.change_pct;
  const shown = items.slice(0, 4).map((i) => ({ item: i, l: listings[i.id] })).filter((x) => x.l);

  return (
    <main className="space-y-6">
      <section className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Rental market overview</h1>
          <p className="text-muted">See how asking rents change over time, then track the places you love.</p>
        </div>
        {updated && <p className="text-sm text-muted">Updated weekly · last {fmtDate(updated)}</p>}
      </section>

      <FilterBar value={filters} onChange={setFilters} />

      <section className={`${cardCls} p-4 sm:p-6`} aria-labelledby="market-h">
        {err && <ErrorNote>{err}</ErrorNote>}
        {!market ? (
          <div className="skeleton h-80" aria-label="Loading market data" />
        ) : (
          <>
            <h2 id="market-h" className="text-sm font-medium text-muted">{label}</h2>
            <p className="mt-1">
              <strong className="text-3xl font-bold tabular-nums tracking-tight">{market.current_value != null ? usd(market.current_value) : "n/a"}</strong>
              <span className="text-muted"> / month</span>
            </p>
            <p className="mb-3 text-sm text-muted">
              {c != null && market.change_since && (
                <span className={`font-semibold ${c > 0 ? "text-warn" : c < 0 ? "text-good" : "text-muted"}`}>
                  {c > 0 ? "↑ Up " : c < 0 ? "↓ Down " : "No change "}{c !== 0 && `${Math.abs(c).toFixed(1)}%`} since {fmtMonth(market.change_since)}
                </span>
              )}
              {c != null && market.change_since && " · "}
              Across {market.active_listings.toLocaleString()} active listings
            </p>
            <RentChart market={market} range={range} onRange={setRange} loading={loading} />
            <div className="mt-3 border-t border-line pt-3">
              <SourceBreakdownView sources={market.sources} sitesOnly={sitesOnly} onToggle={setSitesOnly} />
            </div>
            <ul className="mt-3 space-y-1 text-sm text-muted">
              {market.notes.map((n) => <li key={n}>{n}</li>)}
              <li>
                {filters.beds === "any"
                  ? "With any number of bedrooms this is Zillow's typical-rent index (ZORI) for the area."
                  : "By bedroom count this is the monthly median of asking rents in our listings; months with fewer than 5 listings use Zillow's index instead."}
              </li>
            </ul>
          </>
        )}
      </section>

      <section className="space-y-3" aria-labelledby="saved-h">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="saved-h" className="text-xl font-bold">Saved apartments <span className="text-base font-normal text-muted">· {items.length} tracked</span></h2>
            <p className="text-muted">Your watchlist, with asking-rent history at a glance.</p>
          </div>
          <Link href="/find" className="inline-flex min-h-11 items-center rounded-lg bg-primary px-4 font-semibold text-on-primary hover:bg-primary-hover">+ Save apartment</Link>
        </div>
        {!ready || (savedLoading && shown.length === 0) ? (
          <CardSkeletons />
        ) : shown.length === 0 ? (
          <p className={`${cardCls} p-6 text-center text-muted`}>Nothing saved yet. <Link href="/find" className="font-semibold text-ink underline">Find apartments</Link> to start a watchlist.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {shown.map(({ item, l }) => (
              <ApartmentCard key={item.id} listing={l!} saved={has(item.id)} sinceSaved={item.priceAtSave}
                note={item.example ? "Example: remove anytime" : undefined} onRemove={() => remove(item.id)} />
            ))}
          </div>
        )}
        <p className="text-right"><Link href="/saved" className="inline-flex min-h-11 items-center font-semibold text-accent-strong underline underline-offset-2">View all saved apartments →</Link></p>
      </section>

      <section className="space-y-2" aria-labelledby="map-h">
        <h2 id="map-h" className="text-xl font-bold">Compare neighborhoods</h2>
        <p className="text-muted">Shaded by typical rent. Tap a ZIP to see its 12-month forecast change, then open its profile.</p>
        {map}
      </section>
    </main>
  );
}
