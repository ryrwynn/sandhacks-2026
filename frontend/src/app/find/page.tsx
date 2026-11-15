"use client";
import { useEffect, useRef, useState } from "react";
import ApartmentCard, { CardSkeletons } from "@/components/ApartmentCard";
import FilterBar from "@/components/FilterBar";
import AddArea from "@/components/AddArea";
import AreaSearch from "@/components/AreaSearch";
import Finder from "@/components/Finder";
import { ErrorNote } from "@/components/ui";
import { selectCls, cardCls } from "@/components/styles";
import { errorMessage, getListings } from "@/lib/api";
import { ZIP_OPTIONS } from "@/lib/format";
import { useSaved } from "@/lib/saved";
import { DEFAULT_FILTERS, type Filters } from "@/lib/types";
import type { ListingSort, ListingSummary } from "@/lib/tracker";

const PAGE = 24;

export default function Find() {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<ListingSort>("recent");
  const [items, setItems] = useState<ListingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);   // how many the API has returned so far
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const { has, toggle } = useSaved();
  const [starterOpen, setStarterOpen] = useState(false);   // the Starter finder only loads once opened
  const results = useRef<HTMLDivElement>(null);
  const pickZip = (zip: string) => {
    setFilters((f) => ({ ...f, zip }));
    setStarterOpen(false);
    results.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    results.current?.focus({ preventScroll: true });
  };

  // Deep links such as /find?source=facebook&unit=room preset the source filters.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const source = q.get("source"), unit = q.get("unit");
    if (source === "facebook" || source === "listing_sites" || (unit && ["entire_unit", "room", "sublet"].includes(unit))) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time read of the URL after hydration
      setFilters((f) => ({
        ...f,
        source: source === "facebook" || source === "listing_sites" ? source : f.source,
        unitType: unit === "entire_unit" || unit === "room" || unit === "sublet" ? unit : f.unitType,
      }));
    }
  }, []);

  const seq = useRef(0);   // only the latest request may update the list (filters can change mid-flight)
  const load = (from: number) => {
    const mine = ++seq.current;
    setLoading(true);
    getListings({ zip: filters.zip, beds: filters.beds, type: filters.type, maxPrice: filters.maxPrice || undefined, sort, limit: PAGE, offset: from, source: filters.source, unitType: filters.unitType })
      .then((r) => {
        if (mine !== seq.current) return;
        setErr("");
        setTotal(r.total);
        setOffset(from + r.items.length);
        setItems((cur) => (from === 0 ? r.items : [...cur, ...r.items]));
      })
      .catch((e) => { if (mine === seq.current) setErr(errorMessage(e)); })
      .finally(() => { if (mine === seq.current) setLoading(false); });
  };
  // Reload from the top whenever a filter or the sort changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => load(0), [filters, sort]);

  // This page is about rentals: for-sale records are left out.
  const rentals = items.filter((l) => l.listing_type === "rent");
  const area = ZIP_OPTIONS.find((z) => z.zip === filters.zip)?.name ?? "San Diego";
  const count = Math.max(0, total - (items.length - rentals.length));

  return (
    <main className="space-y-5">
      <section>
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Find apartments</h1>
        <p className="text-muted">Compare asking rents and save the ones you like to watch how their price changes.</p>
      </section>

      <FilterBar value={filters} onChange={setFilters} showPrice showSource />
      {filters.source !== "listing_sites" && (
        <p className="text-sm text-muted">Listings from Facebook groups are marked &ldquo;lower confidence&rdquo;: they come from public posts, have no street address, and count at half weight in our medians.</p>
      )}

      <details data-testid="starter-panel" open={starterOpen} onToggle={(e) => setStarterOpen((e.currentTarget as HTMLDetailsElement).open)}
        className="rounded-xl bg-surface p-3 shadow-[0_1px_3px_rgba(46,49,39,0.12)]">
        <summary className="min-h-11 cursor-pointer py-2.5 text-sm font-semibold">Not sure where to look? Rank the 12 areas for your budget</summary>
        {starterOpen && (
          <div className="pt-2">
            <p className="mb-3 text-sm text-muted">Ranked for low rent and short trips to groceries and transit. Pick an area to see its listings below.</p>
            <Finder persona="starter" onPickZip={pickZip} />
          </div>
        )}
      </details>

      <details className="rounded-xl bg-surface p-3 shadow-[0_1px_3px_rgba(46,49,39,0.12)]">
        <summary className="min-h-11 cursor-pointer py-2.5 text-sm font-semibold">Looking somewhere else? Search another area</summary>
        <div className="pt-2"><AreaSearch /></div>
      </details>

      <div ref={results} tabIndex={-1} className="flex scroll-mt-20 flex-wrap items-center justify-between gap-2 outline-none">
        <h2 className="text-lg font-semibold" aria-live="polite">{loading && items.length === 0 ? "Searching..." : `${count.toLocaleString()} ${filters.unitType === "room" ? "rooms (roommate wanted)" : filters.unitType === "sublet" ? "sublets" : "places"} in ${area}`}</h2>
        <select aria-label="Sort" className={selectCls} value={sort} onChange={(e) => setSort(e.target.value as ListingSort)}>
          <option value="recent">Sort: Recommended</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
          <option value="biggest_drop">Biggest price drop</option>
        </select>
      </div>

      {err && <ErrorNote>{err}</ErrorNote>}
      {loading && items.length === 0 ? (
        <CardSkeletons n={6} />
      ) : rentals.length === 0 && !err ? (
        <div className="space-y-3">
          <p className={`${cardCls} p-8 text-center text-muted`}>No apartments match these filters. Try a higher price limit, any number of bedrooms, or a wider area.</p>
          <AddArea compact />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {rentals.map((l) => <ApartmentCard key={l.id} listing={l} showSave saved={has(l.id)} onToggle={() => toggle(l)} />)}
        </div>
      )}

      {offset < total && items.length > 0 && (
        <div className="text-center">
          <button type="button" disabled={loading} onClick={() => load(offset)} className="min-h-11 rounded-lg bg-surface px-6 font-semibold shadow-[0_1px_3px_rgba(46,49,39,0.2)] hover:bg-line disabled:opacity-50">
            {loading ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
    </main>
  );
}
