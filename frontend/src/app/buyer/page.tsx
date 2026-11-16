import type { Metadata } from "next";
import { Suspense } from "react";
import { getZips, isMock } from "@/lib/api";
import { mapboxToken } from "@/lib/server";
import Finder from "@/components/Finder";
import { MockFlag } from "@/components/ui";

export const metadata: Metadata = { title: "Buyer | RentOrKnot" };

type Q = Promise<Record<string, string | string[] | undefined>>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

async function BuyerFinder({ searchParams }: { searchParams: Q }) {
  const q = await searchParams;
  const budget = /^\d{1,9}$/.test(one(q.budget)) && Number(one(q.budget)) > 0 ? one(q.budget) : undefined;
  const beds = /^[0-3]$/.test(one(q.beds)) ? one(q.beds) : undefined;
  const token = await mapboxToken();
  const zips = await getZips();
  return (
    <>
      <MockFlag on={isMock(zips)} />
      <Finder persona="wealth" token={token} zips={zips.zips} showMap initial={{ budget, beds }} />
    </>
  );
}

export default function BuyerPage({ searchParams }: { searchParams: Q }) {
  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">Wealth builder finder</h1>
      <p className="text-slate-700">Tell us your budget and bedrooms. We rank ZIPs and outline the best ones on the map.</p>
      <Suspense fallback={<div className="h-72 animate-pulse rounded-xl bg-slate-200" />}>
        <BuyerFinder searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
