import type { Metadata } from "next";
import { Suspense } from "react";
import RenterTabs from "@/components/RenterTabs";

export const metadata: Metadata = { title: "Rent increase check | RentOrKnot" };

type Q = Promise<Record<string, string | string[] | undefined>>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

/** An apartment page links here with ?address=&year_built=&zip= so the rent increase check starts filled in. */
async function Tabs({ searchParams }: { searchParams: Q }) {
  const q = await searchParams;
  const year = one(q.year_built);
  return (
    <RenterTabs
      prefill={{
        address: one(q.address).slice(0, 200),
        zip: /^\d{5}$/.test(one(q.zip)) ? one(q.zip) : "",
        year: /^\d{4}$/.test(year) ? year : "",
      }}
    />
  );
}

export default function RenterPage({ searchParams }: { searchParams: Q }) {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Rent increase check</h1>
      <p className="text-muted">Renter tools: check an increase against California&apos;s AB 1482 cap, test a listing&apos;s price, or find a place.</p>
      <Suspense fallback={<div className="skeleton h-96" />}>
        <Tabs searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
