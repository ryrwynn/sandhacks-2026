"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import FilterBar from "@/components/FilterBar";
import RentChart from "@/components/RentChart";
import ApartmentCard from "@/components/ApartmentCard";
import { getListingsByIds, getMarket } from "@/lib/api";
import { useSaved } from "@/lib/saved";
import { DEFAULT_FILTERS, type Filters, type Listing, type Market } from "@/lib/types";

export default function MarketOverview() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [market, setMarket] = useState<Market | null>(null);
  const [saved, setSaved] = useState<Listing[]>([]);
  const { ids, has, toggle } = useSaved();

  useEffect(() => { getMarket(filters).then(setMarket); }, [filters]);
  useEffect(() => { getListingsByIds(ids.slice(0, 4)).then(setSaved); }, [ids]);

  const s = market?.series ?? [];
  const now = s[s.length - 1]?.median ?? 0;
  const since = s.length ? ((now - s[0].median) / s[0].median) * 100 : 0;

  return (
    <>
      <section className="page-head">
        <div>
          <h1>Rental market overview</h1>
          <p className="muted">See how asking rents change over time, then track the places you love.</p>
        </div>
        {market && <span className="muted small">Updated {market.updated}</span>}
      </section>

      <FilterBar value={filters} onChange={setFilters} />

      <section className="card panel">
        <p className="label">Median asking rent</p>
        <div className="stat"><strong>${now.toLocaleString()}</strong><span className="muted"> / month</span></div>
        <p className="muted small">
          {since >= 0 ? "+" : ""}{since.toFixed(1)}% since Jan 2025 · Across {market?.activeListings.toLocaleString() ?? "–"} active listings
        </p>
        {market ? <RentChart key={filters.area + filters.beds} series={market.series} /> : <div className="skeleton" />}
      </section>

      <section className="panel flat">
        <div className="row-between">
          <div>
            <h2>Saved apartments <span className="muted small">{ids.length} tracked</span></h2>
            <p className="muted small">Your watchlist, with asking-rent history at a glance.</p>
          </div>
          <Link href="/find" className="primary">+ Save apartment</Link>
        </div>
        {saved.length === 0 ? (
          <p className="empty">Nothing saved yet. <Link href="/find">Find apartments</Link> to start a watchlist.</p>
        ) : (
          <div className="grid">
            {saved.map((l) => <ApartmentCard key={l.id} listing={l} saved={has(l.id)} onToggle={() => toggle(l.id)} />)}
          </div>
        )}
        <p className="right small"><Link href="/saved">View all saved apartments →</Link></p>
      </section>
    </>
  );
}
