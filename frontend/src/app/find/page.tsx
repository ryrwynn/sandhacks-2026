"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import ApartmentCard, { CardSkeletons } from "@/components/ApartmentCard";
import FilterBar, { MAX_PRICES } from "@/components/FilterBar";
import AddArea from "@/components/AddArea";
import AreaSearch from "@/components/AreaSearch";
import Finder from "@/components/Finder";
import { ErrorNote } from "@/components/ui";
import { selectCls, cardCls } from "@/components/styles";
import { errorMessage, getListings } from "@/lib/api";
import { useAreas } from "@/lib/areas";
import { useSaved } from "@/lib/saved";
import { DEFAULT_FILTERS, type Filters } from "@/lib/types";
import type { ListingSort, ListingSummary } from "@/lib/tracker";

const PER_PAGE = [15, 30, 60] as const;
const SORTS: ListingSort[] = ["recent", "price_asc", "price_desc", "biggest_drop"];

type Query = { filters: Filters; sort: ListingSort; page: number; per: number };

/** Everything on this page lives in the URL, so Back and shared links work. Unknown values fall back to the defaults. */
function readQuery(q: URLSearchParams): Query {
  const source = q.get("source"), unit = q.get("unit"), beds = q.get("beds"), type = q.get("type"), sort = q.get("sort");
  const max = Number(q.get("max")), per = Number(q.get("per")), page = Math.floor(Number(q.get("page")));
  return {
    filters: {
      zip: /^\d{5}$/.test(q.get("zip") ?? "") ? q.get("zip")! : "",
      beds: beds && ["0", "1", "2", "3"].includes(beds) ? beds : "any",
      type: type && ["apartment", "condo", "house"].includes(type) ? type : "any",
      maxPrice: MAX_PRICES.includes(max) ? max : 0,
      source: source === "facebook" || source === "listing_sites" ? source : "all",
      unitType: unit === "entire_unit" || unit === "room" || unit === "sublet" ? unit : "any",
    },
    sort: SORTS.includes(sort as ListingSort) ? (sort as ListingSort) : "recent",
    page: page >= 1 ? page : 1,
    per: (PER_PAGE as readonly number[]).includes(per) ? per : PER_PAGE[0],
  };
}

function toParams(c: Query, starter?: URLSearchParams): string {
  const p = new URLSearchParams();
  const f = c.filters, d = DEFAULT_FILTERS;
  if (f.zip) p.set("zip", f.zip);
  if (f.beds !== d.beds) p.set("beds", f.beds);
  if (f.type !== d.type) p.set("type", f.type);
  if (f.maxPrice) p.set("max", String(f.maxPrice));
  if (f.source && f.source !== d.source) p.set("source", f.source);
  if (f.unitType && f.unitType !== d.unitType) p.set("unit", f.unitType);
  if (c.sort !== "recent") p.set("sort", c.sort);
  if (c.page > 1) p.set("page", String(c.page));
  if (c.per !== PER_PAGE[0]) p.set("per", String(c.per));
  for (const k of ["starter_budget", "starter_beds"]) { const v = starter?.get(k); if (v) p.set(k, v); }
  return p.toString();
}

/** Page numbers with … for gaps: first, last, and the current page with one neighbour each side. */
function pageItems(page: number, pages: number): (number | "gap-l" | "gap-r")[] {
  const keep = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  const out: (number | "gap-l" | "gap-r")[] = [];
  let prev = 0;
  for (const n of [...keep].sort((a, b) => a - b)) {
    if (n - prev === 2) out.push(prev + 1);                          // a single hidden page is shown instead of …
    else if (n - prev > 2) out.push(prev < page ? "gap-l" : "gap-r");
    out.push(n);
    prev = n;
  }
  return out;
}

const pageBtn = "inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg px-3 text-base font-semibold";

function Pagination({ page, pages, onPage }: { page: number; pages: number; onPage: (n: number) => void }) {
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-center gap-1.5">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className={`${pageBtn} bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.2)] hover:bg-line disabled:opacity-40`}>Previous</button>
      {pageItems(page, pages).map((n) =>
        typeof n === "string" ? (
          <span key={n} aria-hidden="true" className="inline-flex min-h-11 min-w-8 items-center justify-center text-muted">…</span>
        ) : (
          <button key={n} type="button" onClick={() => onPage(n)} aria-label={`Page ${n}`} aria-current={n === page ? "page" : undefined}
            className={`${pageBtn} tabular-nums ${n === page ? "bg-primary text-on-primary" : "bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.2)] hover:bg-line"}`}>{n}</button>
        ),
      )}
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)} className={`${pageBtn} bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.2)] hover:bg-line disabled:opacity-40`}>Next</button>
    </nav>
  );
}

function FindPage() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const cur = useMemo(() => readQuery(new URLSearchParams(search.toString())), [search]);
  const { filters, sort, page, per } = cur;
  const [items, setItems] = useState<ListingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const { has, toggle } = useSaved();
  const areas = useAreas();

  // ?starter_budget= and ?starter_beds= open the Starter finder and fill it in (it ranks areas only; nothing else runs).
  const starterBudget = search.get("starter_budget"), starterBeds = search.get("starter_beds");
  const [starterOpen, setStarterOpen] = useState(!!(starterBudget || starterBeds));
  const starterInit = useRef({
    budget: starterBudget && /^\d+$/.test(starterBudget) ? starterBudget : undefined,
    beds: starterBeds && ["0", "1", "2", "3"].includes(starterBeds) ? starterBeds : undefined,
  });

  const wrap = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const focusNext = useRef(false);
  const toResults = () => {
    wrap.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    heading.current?.focus({ preventScroll: true });
  };

  /** Write a new query to the URL. Filters and sort go back to page 1; a page change adds a history entry. */
  const go = (patch: Partial<Query>, opts: { keepPage?: boolean } = {}) => {
    const next = { ...cur, ...patch };
    if (!opts.keepPage && patch.page === undefined) next.page = 1;
    const qs = toParams(next, new URLSearchParams(search.toString()));
    const url = qs ? `${pathname}?${qs}` : pathname;
    if (patch.page !== undefined) router.push(url, { scroll: false });
    else router.replace(url, { scroll: false });
  };

  const pickZip = (zip: string) => {
    go({ filters: { ...filters, zip } });
    setStarterOpen(false);
    focusNext.current = true;
  };
  const changePage = (n: number) => { focusNext.current = true; go({ page: n }); };

  const seq = useRef(0);   // only the latest request may update the list (the URL can change mid-flight)
  const key = JSON.stringify([filters, sort, page, per]);
  useEffect(() => {
    const mine = ++seq.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag for the request started here
    setLoading(true);
    getListings({ zip: filters.zip, beds: filters.beds, type: filters.type, maxPrice: filters.maxPrice || undefined, sort, limit: per, offset: (page - 1) * per, source: filters.source, unitType: filters.unitType })
      .then((r) => {
        if (mine !== seq.current) return;
        setErr("");
        setTotal(r.total);
        setItems(r.items);
        const pages = Math.max(1, Math.ceil(r.total / per));
        if (page > pages) go({ page: pages });                    // a shared link past the last page lands on the last one
      })
      .catch((e) => { if (mine === seq.current) setErr(errorMessage(e)); })
      .finally(() => {
        if (mine !== seq.current) return;
        setLoading(false);
        if (focusNext.current) { focusNext.current = false; requestAnimationFrame(toResults); }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // This page is about rentals: for-sale records are left out.
  const rentals = items.filter((l) => l.listing_type === "rent");
  const area = areas.find((z) => z.zip === filters.zip)?.name ?? "San Diego";
  const pages = Math.max(1, Math.ceil(total / per));
  const from = total === 0 ? 0 : (page - 1) * per + 1;
  const to = Math.min(total, (page - 1) * per + items.length);

  return (
    <main className="space-y-5">
      <section>
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Find apartments</h1>
        <p className="text-muted">Compare asking rents and save the ones you like to watch how their price changes.</p>
      </section>

      <FilterBar value={filters} onChange={(f) => go({ filters: f })} showPrice priceAlways showSource />
      {filters.source !== "listing_sites" && (
        <p className="text-sm text-muted">Listings from Facebook groups are marked &ldquo;lower confidence&rdquo;: they come from public posts, have no street address, and count at half weight in our medians.</p>
      )}

      <details data-testid="starter-panel" open={starterOpen} onToggle={(e) => setStarterOpen((e.currentTarget as HTMLDetailsElement).open)}
        className="rounded-xl bg-surface p-3 shadow-[0_1px_3px_rgba(46,49,39,0.12)]">
        <summary className="min-h-11 cursor-pointer py-2.5 text-sm font-semibold">Not sure where to look? Rank areas for your budget</summary>
        {starterOpen && (
          <div className="pt-2">
            <p className="mb-3 text-sm text-muted">Ranked for low rent and short trips to groceries and transit. Pick an area to see its listings below.</p>
            <Finder persona="starter" onPickZip={pickZip} initial={starterInit.current} />
          </div>
        )}
      </details>

      <details className="rounded-xl bg-surface p-3 shadow-[0_1px_3px_rgba(46,49,39,0.12)]">
        <summary className="min-h-11 cursor-pointer py-2.5 text-sm font-semibold">Looking somewhere else? Search another area</summary>
        <div className="pt-2"><AreaSearch /></div>
      </details>

      <div ref={wrap} className="flex scroll-mt-20 flex-wrap items-center justify-between gap-2">
        <h2 ref={heading} tabIndex={-1} className="text-lg font-semibold outline-none" aria-live="polite">{loading && items.length === 0 ? "Searching..." : `${total.toLocaleString()} ${filters.unitType === "room" ? "rooms (roommate wanted)" : filters.unitType === "sublet" ? "sublets" : "places"} in ${area}`}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Sort" className={selectCls} value={sort} onChange={(e) => go({ sort: e.target.value as ListingSort })}>
            <option value="recent">Sort: Recommended</option>
            <option value="price_asc">Price: low to high</option>
            <option value="price_desc">Price: high to low</option>
            <option value="biggest_drop">Biggest price drop</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-muted">
            Per page
            <select className={selectCls} value={per} onChange={(e) => go({ per: Number(e.target.value) })}>
              {PER_PAGE.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
      </div>
      {total > 0 && items.length > 0 && <p className="text-sm text-muted" data-testid="find-showing">Showing {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}</p>}

      {err && <ErrorNote>{err}</ErrorNote>}
      {loading && items.length === 0 ? (
        <CardSkeletons n={6} />
      ) : rentals.length === 0 && !err ? (
        <div className="space-y-3">
          <p className={`${cardCls} p-8 text-center text-muted`}>No apartments match these filters. Try a higher price limit, any number of bedrooms, or a wider area.</p>
          <AddArea compact />
        </div>
      ) : (
        <div className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${loading ? "opacity-60" : ""}`}>
          {rentals.map((l) => <ApartmentCard key={l.id} listing={l} showSave saved={has(l.id)} onToggle={() => toggle(l)} />)}
        </div>
      )}

      <Pagination page={page} pages={pages} onPage={changePage} />
    </main>
  );
}

export default function Find() {
  return <Suspense fallback={<CardSkeletons n={6} />}><FindPage /></Suspense>;
}
