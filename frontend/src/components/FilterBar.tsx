"use client";
import { useState } from "react";
import type { Filters } from "@/lib/types";
import { ZIP_OPTIONS } from "@/lib/format";
import { selectCls } from "./styles";

export default function FilterBar({ value, onChange, showPrice, showSource }: {
  value: Filters; onChange: (f: Filters) => void; showPrice?: boolean; showSource?: boolean;
}) {
  const [more, setMore] = useState(value.maxPrice > 0);
  const set = (patch: Partial<Filters>) => onChange({ ...value, ...patch });
  return (
    <div role="group" aria-label="Filters" className="space-y-2">
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <select aria-label="Area" className={`${selectCls} col-span-2 sm:col-span-1 sm:min-w-52`} value={value.zip} onChange={(e) => set({ zip: e.target.value })}>
          <option value="">All San Diego areas</option>
          {ZIP_OPTIONS.map((z) => <option key={z.zip} value={z.zip}>{z.name} ({z.zip})</option>)}
        </select>
        <select aria-label="Bedrooms" className={selectCls} value={value.beds} onChange={(e) => set({ beds: e.target.value })}>
          <option value="any">Any bedrooms</option>
          <option value="0">Studio</option>
          <option value="1">1 bedroom</option>
          <option value="2">2 bedrooms</option>
          <option value="3">3 bedrooms</option>
        </select>
        <select aria-label="Property type" className={selectCls} value={value.type} onChange={(e) => set({ type: e.target.value })}>
          <option value="any">All property types</option>
          <option value="apartment">Apartment</option>
          <option value="condo">Condo</option>
          <option value="house">House</option>
        </select>
        {showSource && (
          <>
            <select aria-label="Source" className={selectCls} value={value.source ?? "all"} onChange={(e) => set({ source: e.target.value as Filters["source"] })}>
              <option value="all">All sources</option>
              <option value="listing_sites">Listing sites</option>
              <option value="facebook">Facebook groups</option>
            </select>
            <select aria-label="Whole unit or room" className={selectCls} value={value.unitType ?? "any"} onChange={(e) => set({ unitType: e.target.value as Filters["unitType"] })}>
              <option value="any">Whole units and rooms</option>
              <option value="entire_unit">Whole units only</option>
              <option value="room">Rooms only</option>
              <option value="sublet">Sublets only</option>
            </select>
          </>
        )}
        {showPrice && (
          <button type="button" aria-expanded={more} onClick={() => setMore((m) => !m)} className="min-h-11 rounded-lg px-3 text-base font-medium text-accent-strong underline underline-offset-2">
            {more ? "Fewer filters" : "More filters"}
          </button>
        )}
      </div>
      {showPrice && more && (
        <select aria-label="Max price" className={selectCls} value={value.maxPrice} onChange={(e) => set({ maxPrice: Number(e.target.value) })}>
          <option value={0}>Any price</option>
          {[2000, 2500, 3000, 3500, 4000, 5000].map((p) => <option key={p} value={p}>Up to ${p.toLocaleString()} a month</option>)}
        </select>
      )}
    </div>
  );
}
