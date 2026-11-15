import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { getZipProfile, getZipSeries, getZips, isMock } from "@/lib/api";
import { mapboxToken } from "@/lib/server";
import { pct, usd } from "@/lib/format";
import ForecastChart from "@/components/ForecastChart";
import ZipMap from "@/components/ZipMap";
import { ScoreCard } from "@/components/cards";
import { Card, Disclaimer, MockFlag } from "@/components/ui";
import ScenarioPanel from "@/components/ScenarioPanel";
import { ZipTrends } from "@/components/Trends";
import { ZipSourceCard } from "@/components/SourceBreakdown";
import { getAreas, getZipSeriesScenarios } from "@/lib/night-api";
import AddArea from "@/components/AddArea";

export const metadata: Metadata = { title: "ZIP profile | RentOrKnot" };

const TIER_TEXT: Record<string, string> = {
  county: "County coverage: typical rent and home value from Zillow Research, plus listings we've sampled",
  index: "California index coverage: typical rent and home value from Zillow Research",
  on_demand: "Added on request: typical rent and home value from Zillow Research",
};

async function CoveredZip({ zip, token, all }: { zip: string; token: string | null; all: import("@/lib/contract").ZipSummary[] }) {
  const r = await getAreas({ q: zip, limit: 5 }).catch(() => null);
  const a = r && !isMock(r) ? r.areas.find((x) => x.geo_type === "zip" && x.geo_id === zip) : undefined;
  if (!a) {
    return (
      <>
        <h1 className="text-xl font-bold sm:text-2xl">ZIP {zip}</h1>
        <p className="text-muted">We don&apos;t cover this ZIP yet. You can ask for it below; nothing is posted anywhere.</p>
        <AddArea compact />
        <Link href="/" className="inline-block text-sm text-accent-strong underline">Back to the map</Link>
      </>
    );
  }
  const center: [number, number] | undefined = a.centroid_lng != null && a.centroid_lat != null ? [a.centroid_lng, a.centroid_lat] : undefined;
  return (
    <>
      <h1 className="text-xl font-bold sm:text-2xl">{zip} {a.name}</h1>
      <p className="text-muted">{a.county ? `${a.county} County · ` : ""}{TIER_TEXT[a.tier] ?? "Covered area"}. Forecasts, scores and the listing tracker cover the 12 core San Diego ZIPs.</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Typical rent (ZORI)" value={usd(a.typical_rent_usd)} />
        <Stat label="Typical home value (ZHVI)" value={usd(a.typical_home_value_usd)} />
        {a.last_scraped_at && <Stat label="Listings last sampled" value={new Date(a.last_scraped_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })} />}
      </div>
      <ZipMap token={token} zips={all} focus={zip} focusCenter={center} heightClass="h-56 sm:h-72" />
      <Disclaimer kind="estimate" />
      <Link href="/areas" className="inline-block text-sm text-accent-strong underline">All covered areas</Link>
    </>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-surface p-3">
      <div className="text-xs text-slate-600">{label}</div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
      {note && <div className="text-xs text-slate-500">{note}</div>}
    </div>
  );
}

const AMENITIES: [keyof import("@/lib/contract").AmenityCounts, string][] = [
  ["groceries", "Grocery stores"], ["transit_stops", "Transit stops"], ["parks", "Parks"], ["food_drink", "Cafes and restaurants"], ["gyms", "Gyms"],
];

async function Zip({ params }: { params: Promise<{ zip: string }> }) {
  const { zip } = await params;
  const token = await mapboxToken();
  const [p, rent, value, all] = await Promise.all([getZipProfile(zip), getZipSeries(zip, "zori"), getZipSeries(zip, "zhvi"), getZips()]);
  // Full profiles exist for the 12 core ZIPs. Any other ZIP: show what coverage knows (or say it isn't covered)
  // instead of sample data.
  if (isMock(p) && /^\d{5}$/.test(zip) && !isMock(all) && !all.zips.some((z) => z.zip === zip)) {
    return <CoveredZip zip={zip} token={token} all={all.zips} />;
  }
  const mock = [p, rent, value, all].some(isMock);
  // Measured 80% coverage from the latest training (served baseline); shown on each chart.
  const [covRent, covValue] = await Promise.all((["zori", "zhvi"] as const).map((m) =>
    getZipSeriesScenarios(zip, m, "baseline").then((r) => (isMock(r) ? null : r.coverage_80 ?? null)).catch(() => null)));
  return (
    <>
      <MockFlag on={mock} />
      <h1 className="text-xl font-bold sm:text-2xl">{p.zip} {p.name}</h1>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Typical rent" value={usd(p.typical_rent_usd)} note={`${pct(p.rent_forecast_change_pct, 1, true)} in 12 months`} />
        <Stat label="Typical home value" value={usd(p.typical_home_value_usd)} note={`${pct(p.value_forecast_change_pct, 1, true)} in 12 months`} />
        <Stat label="Gross rental yield" value={pct(p.gross_yield_pct)} note="12 x rent / home value" />
        <Stat label="Listings, last 30 days" value={String(p.listings_30d)} />
      </div>
      <ZipMap token={token} zips={all.zips} focus={p.zip} heightClass="h-56 sm:h-72" />
      <ZipSourceCard zip={p.zip} />
      <Card><ForecastChart series={rent} title="Typical rent" coverage={covRent} /></Card>
      <Card><ForecastChart series={value} title="Typical home value" coverage={covValue} /></Card>
      <ScenarioPanel zip={p.zip} />
      <ZipTrends zip={p.zip} />
      <section className="space-y-3">
        <h2 className="text-lg font-bold">Scores for this ZIP</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <ScoreCard title="Starter finder" score={p.persona_scores.starter} subtitle="Low rent and short trips to basics" />
          <ScoreCard title="Wealth builder" score={p.persona_scores.wealth} subtitle="Appreciation, yield and budget fit" />
        </div>
        <p className="text-xs text-slate-600">Scores use prices, forecasts, listings and amenities only, never who lives in a ZIP.</p>
      </section>
      <Card>
        <h2 className="mb-2 text-lg font-bold">Rent by bedrooms (listings, last 30 days)</h2>
        <p className="mb-2 text-xs text-muted">Listing sites, plus whole units from Facebook groups at half weight. Rooms, sublets and unusual prices are left out.</p>
        <dl className="grid grid-cols-4 gap-2 text-center text-sm">
          {(["0", "1", "2", "3"] as const).map((b) => (
            <div key={b}><dt className="text-xs text-slate-600">{b === "0" ? "Studio" : `${b} bed`}</dt><dd className="font-semibold tabular-nums">{usd(p.median_rent_by_beds[b])}</dd></div>
          ))}
        </dl>
      </Card>
      <Card>
        <h2 className="mb-2 text-lg font-bold">Amenities</h2>
        <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {AMENITIES.map(([k, label]) => (
            <li key={k} className="flex justify-between"><span>{label}</span><span className="tabular-nums font-semibold">{p.amenities[k] ?? "n/a"}</span></li>
          ))}
        </ul>
      </Card>
      <Card>
        <h2 className="mb-2 text-lg font-bold">Rent burden</h2>
        <p className="text-sm">
          Typical rent is about <b>{pct(p.rent_burden_pct)}</b> of the ZIP&apos;s median monthly household income{p.median_income_usd != null && <> ({usd(p.median_income_usd)} a year)</>}. This is context only and is not part of any score.
        </p>
      </Card>
      <Disclaimer kind="estimate" />
      <Link href="/" className="inline-block text-sm text-indigo-700 underline">Back to the map</Link>
    </>
  );
}

export default function ZipPage(props: PageProps<"/zip/[zip]">) {
  return (
    <main className="space-y-4">
      <Suspense fallback={<div className="h-72 animate-pulse rounded-xl bg-slate-200" />}>
        <Zip params={props.params} />
      </Suspense>
    </main>
  );
}
