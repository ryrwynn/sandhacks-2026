import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { connection } from "next/server";
import { getHealth, isMock } from "@/lib/api";
import { usd } from "@/lib/format";
import { Card, Disclaimer, MockFlag } from "@/components/ui";

export const metadata: Metadata = { title: "About | RentOrKnot" };

// Public names from sources/facebook_groups/groups.yaml (groups that answered without a login on 2026-11-15).
const FB_GROUPS = [
  "San Diego Housing, Rooms, Apartments, Sublets",
  "San Diego Apartments & Housing (NO SPAM)",
  "San Diego Housing, Rooms, Apartments, Sublets, Roomster",
  "San Diego Housing, Rooms, Apartments, Sublets (Neighborly Group)",
  "San Diego Sublets",
  "San Diego Roommates",
];   // "UCSD Student Off-Campus Housing" is private (checked 2026-11-15), so it is not read.

const SOURCES = [
  ["Zillow rental and for-sale listings", "Rent, bedrooms, size, year built and price history for 12 San Diego ZIP codes. Rentals are updated weekly (Thursdays), for-sale listings daily."],
  ["Zillow Research ZORI and ZHVI", "Monthly typical rent and typical home value by ZIP, with years of history. Used for trends and forecasts."],
  ["Census ACS 5-year", "Median household income and median gross rent. Shown as context, never used in a score."],
  ["OpenStreetMap", "Counts of grocery stores, transit stops, parks, cafes and restaurants, and gyms per ZIP."],
  ["Public Facebook rental groups", "Rental offers posted in the public groups listed below. An AI model reads each post for price, bedrooms, unit type and area; we keep only those fields and a link to the post. Post text, names, profile links and photos are never stored or shown."],
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
      <Card className="space-y-2">
        <h2 className="text-lg font-bold">Facebook groups we read</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {FB_GROUPS.map((g) => <li key={g}>{g}</li>)}
        </ul>
        <p className="text-sm">
          Only public groups, read without signing in. A post becomes a listing when it offers a place for rent and states a
          price, the number of bedrooms and a San Diego area. Posts give no street address, so these listings are marked
          &ldquo;lower confidence&rdquo; and placed by ZIP code only.
        </p>
        <p className="text-sm">
          In our medians and counts a whole-unit Facebook listing counts at half the weight of a listing-site listing. Rooms
          and sublets are counted separately and never mixed into whole-unit rents. A price below 40% or above 250% of the
          listing-site median for the same ZIP and bedroom count is marked &ldquo;unusual price&rdquo; and left out of
          medians. Reposts of the same offer within 30 days become its price history; an offer not reposted for 21 days is
          shown as inactive. Market cards have a &ldquo;Listing sites only&rdquo; switch. Facebook listings never train the
          fair-rent model and never feed building facts or the rent-cap check.
        </p>
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
      <p className="text-sm text-muted">See our <Link href="/privacy" className="underline">Privacy</Link> and <Link href="/terms" className="underline">Terms</Link>.</p>
    </main>
  );
}
