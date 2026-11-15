"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ApartmentCard from "@/components/ApartmentCard";
import { getListingsByIds } from "@/lib/api";
import { useSaved } from "@/lib/saved";
import type { Listing } from "@/lib/types";

export default function Saved() {
  const { ids, has, toggle } = useSaved();
  const [items, setItems] = useState<Listing[]>([]);
  useEffect(() => { getListingsByIds(ids).then(setItems); }, [ids]);

  return (
    <>
      <section className="page-head">
        <div>
          <h1>Saved apartments</h1>
          <p className="muted">Apartments to be tracked over time</p>
        </div>
        <Link href="/find" className="primary">+ Save apartment</Link>
      </section>
      {items.length === 0 ? (
        <p className="empty">No saved apartments yet. <Link href="/find">Find apartments</Link> and save the ones you like.</p>
      ) : (
        <div className="grid">
          {items.map((l) => <ApartmentCard key={l.id} listing={l} saved={has(l.id)} onToggle={() => toggle(l.id)} />)}
        </div>
      )}
    </>
  );
}
