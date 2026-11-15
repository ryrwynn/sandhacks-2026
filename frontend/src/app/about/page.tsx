import type { Metadata } from "next";
import { Suspense } from "react";
import { connection } from "next/server";
import { getHealth, isMock } from "@/lib/api";
import { usd } from "@/lib/format";
import { Card, Disclaimer, MockFlag } from "@/components/ui";

export const metadata: Metadata = { title: "About | RentOrKnot" };

const SOURCES = [
  ["Zillow rental and for-sale listings", "Rent, bedrooms, size, year built and price history, collected every few hours for 12 San Diego ZIP codes."],
  ["Zillow Research ZORI and ZHVI", "Monthly typical rent and typical home value by ZIP, with years of history. Used for trends and forecasts."],
  ["Census ACS 5-year", "Median household income and median gross rent. Shown as context, never used in a score."],
  ["OpenStreetMap", "Counts of grocery stores, transit stops, parks, cafes and restaurants, and gyms per ZIP."],
  ["Census ZIP boundaries", "ZCTA shapes for the map."],
  ["AB 1482 cap table", "San Diego County caps by date, with sources."],
];

async function Models() {
  await connection();
  const h = await getHealth();
  const fair = h.model_runs.find((m) => m.kind === "fair_rent");
  const fc = h.model_runs.find((m) => m.kind === "forecast");
  return (
    <Card className="space-y-2">
      <MockFlag on={isMock(h)} />
      <h2 className="text-lg font-bold">How accurate are the models?</h2>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {fair && (
          <li>
            Fair-rent model: typically off by about {usd(fair.metrics.mae_usd)} on rents it hadn&apos;t seen
            {fair.metrics.coverage_80 != null && <>; {Math.round(fair.metrics.coverage_80 * 100)}% of those rents fell inside the 80% range</>}
            {fair.n_rows != null && <> (trained on {fair.n_rows.toLocaleString()} listings)</>}.
          </li>
        )}
        {fc && <li>Forecasts: median error on the past 12 months of {fc.metrics.median_mape?.toFixed(1)}%, checked against a &quot;next year equals this month&quot; baseline on each ZIP page.</li>}
        {!fair && !fc && <li>Model runs are not available yet.</li>}
      </ul>
      <p className="text-xs text-slate-600">
        Data status: {h.status}. {h.last_scrape_at ? `Last listing update ${new Date(h.last_scrape_at).toLocaleString("en-US", { timeZone: "America/Los_Angeles" })} Pacific.` : ""}
      </p>
    </Card>
  );
}

export default function AboutPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">About RentOrKnot</h1>
      <p className="text-slate-700">RentOrKnot reads public rental and home-price data and explains it. It never contacts landlords or posts anything anywhere.</p>
      <Card>
        <h2 className="mb-2 text-lg font-bold">Data sources</h2>
        <ul className="space-y-2 text-sm">
          {SOURCES.map(([t, d]) => (
            <li key={t}><b>{t}.</b> {d}</li>
          ))}
        </ul>
      </Card>
      <Suspense fallback={<div className="h-32 animate-pulse rounded-xl bg-slate-200" />}>
        <Models />
      </Suspense>
      <Card className="space-y-2">
        <h2 className="text-lg font-bold">What the answers are, and aren&apos;t</h2>
        <p className="text-sm">Rent-increase checks apply California&apos;s AB 1482 rules to the numbers you enter. Text explaining a result is written by an AI model and checked against those numbers.</p>
        <p className="text-sm">Prices, forecasts and scores are estimates with ranges, based on public data. Scores never use who lives in a ZIP.</p>
        <Disclaimer kind="legal" />
        <Disclaimer kind="estimate" />
      </Card>
    </main>
  );
}
