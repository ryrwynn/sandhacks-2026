import Link from "next/link";
import { Suspense } from "react";
import { getZips, isMock } from "@/lib/api";
import { mapboxToken } from "@/lib/server";
import ZipMap from "@/components/ZipMap";
import { MockFlag } from "@/components/ui";

const MODES = [
  { href: "/renter", title: "I rent", body: "Check a rent increase, get a reply letter, test a listing's price, or find a place." },
  { href: "/buyer", title: "I want to buy", body: "Find ZIPs that build wealth: expected appreciation, rental yield and fit to your budget." },
  { href: "/owner", title: "I own", body: "See where your price sits, the legal maximum for an occupied unit, and how complete your listing is." },
];

async function MapSection() {
  const token = await mapboxToken();
  const zips = await getZips();
  return (
    <>
      <MockFlag on={isMock(zips)} />
      <ZipMap token={token} zips={zips.zips} />
    </>
  );
}

export default function Home() {
  return (
    <main className="space-y-6">
      <section>
        <h1 className="text-2xl font-bold leading-tight">San Diego rent and home prices, in plain numbers</h1>
        <p className="mt-1 text-slate-700">Pick what you are doing. Every number comes with a range and the data behind it.</p>
      </section>
      <div className="grid gap-3 sm:grid-cols-3">
        {MODES.map((m) => (
          <Link key={m.href} href={m.href} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm active:bg-slate-50">
            <h2 className="text-lg font-bold text-indigo-800">{m.title}</h2>
            <p className="mt-1 text-sm text-slate-700">{m.body}</p>
          </Link>
        ))}
      </div>
      <section className="space-y-2">
        <h2 className="text-lg font-bold">Typical rent by ZIP</h2>
        <Suspense fallback={<div className="h-72 animate-pulse rounded-xl bg-slate-200" />}>
          <MapSection />
        </Suspense>
      </section>
    </main>
  );
}
