"use client";
import type { Filters } from "@/lib/types";
import { AREAS } from "@/lib/mock";

export default function FilterBar({ value, onChange, showPrice }: {
  value: Filters; onChange: (f: Filters) => void; showPrice?: boolean;
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...value, ...patch });
  return (
    <div className="filters" role="group" aria-label="Filters">
      <select aria-label="Area" value={value.area} onChange={(e) => set({ area: e.target.value })}>
        {AREAS.map((a) => <option key={a}>{a}</option>)}
      </select>
      <select aria-label="Bedrooms" value={value.beds} onChange={(e) => set({ beds: e.target.value })}>
        <option value="any">Any bedrooms</option>
        <option value="0">Studio</option>
        <option value="1">1 bedroom</option>
        <option value="2">2 bedrooms</option>
        <option value="3">3 bedrooms</option>
      </select>
      {showPrice && (
        <select aria-label="Max price" value={value.maxPrice} onChange={(e) => set({ maxPrice: Number(e.target.value) })}>
          <option value={0}>Any price</option>
          {[2500, 3000, 3500, 4000].map((p) => <option key={p} value={p}>Up to ${p.toLocaleString()}</option>)}
        </select>
      )}
      <select aria-label="Property type" value={value.type} onChange={(e) => set({ type: e.target.value })}>
        <option value="any">All property types</option>
        <option value="apartment">Apartment</option>
        <option value="condo">Condo</option>
        <option value="house">House</option>
      </select>
      <button className="ghost">More filters</button>
    </div>
  );
}
