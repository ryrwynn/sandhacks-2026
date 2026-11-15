"use client";
import { useEffect, useMemo, useState } from "react";
import FilterBar from "@/components/FilterBar";
import ApartmentCard from "@/components/ApartmentCard";
import { getListings } from "@/lib/api";
import { useSaved } from "@/lib/saved";
import { DEFAULT_FILTERS, type Filters, type Listing } from "@/lib/types";

export default function Find() {
  const [filters, setFilters] = useState<Filters>({ ...DEFAULT_FILTERS, maxPrice: 3500 });
  const [sort, setSort] = useState("recommended");
  const [items, setItems] = useState<Listing[]>([]);
  const { has, toggle } = useSaved();

  useEffect(() => { getListings(filters).then(setItems); }, [filters]);

  const sorted = useMemo(() => {
    const c = [...items];
    if (sort === "low") c.sort((a, b) => a.rent - b.rent);
    if (sort === "high") c.sort((a, b) => b.rent - a.rent);
    if (sort === "drop") c.sort((a, b) => (a.rent - a.history[0]) - (b.rent - b.history[0]));
    return c;
  }, [items, sort]);

  return (
    <>
      <section className="page-head">
        <div>
          <h1>Find apartments</h1>
          <p className="muted">Find your next place, compare asking rents, and save the ones you love.</p>
        </div>
      </section>
      <FilterBar value={filters} onChange={setFilters} showPrice />
      <div className="row-between results-bar">
        <div>
          <h2 className="small-h">{sorted.length} apartments in {filters.area.split(",")[0]}</h2>
          <p className="muted small">Compare six-month rent trends before adding a place to your watchlist.</p>
        </div>
        <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="recommended">Sort: Recommended</option>
          <option value="low">Price: low to high</option>
          <option value="high">Price: high to low</option>
          <option value="drop">Biggest price drop</option>
        </select>
      </div>
      {sorted.length === 0 ? (
        <p className="empty">No apartments match these filters. Try a higher price limit or more bedrooms.</p>
      ) : (
        <div className="grid">
          {sorted.map((l) => <ApartmentCard key={l.id} listing={l} showSave saved={has(l.id)} onToggle={() => toggle(l.id)} />)}
        </div>
      )}
    </>
  );
}
