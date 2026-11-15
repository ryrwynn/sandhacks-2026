"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import ApartmentCard, { CardSkeletons } from "@/components/ApartmentCard";
import { selectCls, cardCls } from "@/components/styles";
import { useSaved } from "@/lib/saved";

type Sort = "recent" | "price" | "drop";

export default function Saved() {
  const { items, listings, ready, loading, has, remove } = useSaved();
  const [sort, setSort] = useState<Sort>("recent");

  const rows = useMemo(() => {
    const r = items.map((item) => ({ item, l: listings[item.id] })).filter((x) => x.l);
    if (sort === "price") r.sort((a, b) => a.l.current_price_usd - b.l.current_price_usd);
    if (sort === "drop") r.sort((a, b) => (a.l.current_price_usd - a.item.priceAtSave) - (b.l.current_price_usd - b.item.priceAtSave));
    return r;   // "recent": items are stored newest first
  }, [items, listings, sort]);

  return (
    <main className="space-y-5">
      <section className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Saved apartments</h1>
          <p className="text-muted">Apartments you are tracking. They are saved in this browser only.</p>
        </div>
        <div className="flex items-center gap-2">
          {items.length > 1 && (
            <select aria-label="Sort saved apartments" className={selectCls} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="recent">Recently saved</option>
              <option value="price">Price: low to high</option>
              <option value="drop">Biggest drop since saved</option>
            </select>
          )}
          <Link href="/find" className="inline-flex min-h-11 items-center rounded-lg bg-primary px-4 font-semibold text-on-primary hover:bg-primary-hover">+ Save apartment</Link>
        </div>
      </section>

      {!ready || (loading && rows.length === 0) ? (
        <CardSkeletons n={4} />
      ) : items.length === 0 ? (
        <div className={`${cardCls} p-8 text-center`}>
          <p className="text-lg font-semibold">Nothing saved yet.</p>
          <p className="mb-4 text-muted">Find apartments to start a watchlist.</p>
          <Link href="/find" className="inline-flex min-h-11 items-center rounded-lg bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover">Find apartments</Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map(({ item, l }) => (
            <ApartmentCard key={item.id} listing={l} saved={has(item.id)} sinceSaved={item.priceAtSave}
              note={item.example ? "Example: remove anytime" : undefined} onRemove={() => remove(item.id)} />
          ))}
        </div>
      )}
      {ready && items.length > 0 && rows.length < items.length && !loading && (
        <p className="text-sm text-muted">{items.length - rows.length} saved apartment{items.length - rows.length === 1 ? " is" : "s are"} no longer in our data and can&apos;t be shown.</p>
      )}
    </main>
  );
}
