import Link from "next/link";
import type { CheckResponse, Contribution, ListingAnalysisResponse, ListingEvalResponse, RankedZip, Verdict } from "@/lib/contract";
import { pct, usd } from "@/lib/format";
import { Bar, Card, Disclaimer } from "./ui";

/** A contribution's raw value in words: at most 2 decimals, ratios as percentages. Unknown features show nothing. */
export function contributionValue(c: Contribution): string | null {
  const v = c.value;
  if (v == null || !Number.isFinite(v)) return null;
  switch (c.feature) {
    case "value_forecast": return `${pct(v, 1, true)} in 12 months`;
    case "rent_forecast": return `${pct(v, 1, true)} in 12 months`;
    case "gross_yield": return `${pct(v * 100, 2)} gross yield`;
    case "value_vs_budget": return `${pct(v * 100, 0)} of your budget`;
    case "volatility": return `prices move about ${pct(v, 2)} a month`;
    case "rent": return `${usd(v)} / month`;
    case "basics_density":
    case "other_amenities_density": return `${v.toFixed(1)} per km²`;
    case "listings_30d": return `${Math.round(v)} listings`;
    default: return null;
  }
}

/** Score 0 to 100 with the points each factor added. Used for ranked ZIPs and persona scores. */
export function ScoreCard({
  title, score, subtitle, contributions, summary, href, stretch,
}: {
  title: string; score: number | null | undefined; subtitle?: string; contributions?: Contribution[];
  summary?: string | null; href?: string; stretch?: boolean;
}) {
  return (
    <Card className={stretch ? "border-dashed" : ""}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{href ? <Link href={href} className="underline decoration-slate-300 underline-offset-2">{title}</Link> : title}</h3>
          {subtitle && <p className="text-sm text-slate-600">{subtitle}</p>}
        </div>
        <div className="text-right" aria-label={`Score ${score == null ? "not available" : Math.round(score)} out of 100`}>
          <div className="text-xl font-bold tabular-nums text-indigo-800">{score == null ? "n/a" : Math.round(score)}</div>
          <div className="text-xs text-slate-500">of 100</div>
        </div>
      </div>
      {summary && <p className="mt-2 text-sm text-slate-800">{summary}</p>}
      {contributions && contributions.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-slate-700">
          {contributions.map((c) => (
            <li key={c.feature} className="flex justify-between gap-2">
              <span>
                {c.label}
                {contributionValue(c) && <span className="block text-xs text-slate-500">{contributionValue(c)}</span>}
              </span>
              <span className="shrink-0 tabular-nums text-slate-500">+{c.points.toFixed(1)} pts</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function RankedZipCard({ z, stretch, priceLabel }: { z: RankedZip; stretch?: boolean; priceLabel: string }) {
  return (
    <ScoreCard
      title={`${z.rank}. ${z.zip} ${z.name}`}
      score={z.score}
      subtitle={z.price_usd != null ? `${priceLabel} ${usd(z.price_usd)}` : undefined}
      contributions={z.top_contributions}
      summary={z.summary}
      href={`/zip/${z.zip}`}
      stretch={stretch}
    />
  );
}

const VERDICT: Record<Verdict, { title: string; tone: string; lead: string }> = {
  over_cap: { title: "Over the cap", tone: "border-red-300 bg-red-50", lead: "This increase is above what AB 1482 allows." },
  within_cap: { title: "Within the cap", tone: "border-emerald-300 bg-emerald-50", lead: "This increase is within what AB 1482 allows." },
  not_covered: { title: "Not covered by AB 1482", tone: "border-slate-300 bg-slate-100", lead: "From what you entered, the state rent cap does not apply to this unit." },
  unclear: { title: "Can't tell yet", tone: "border-amber-300 bg-amber-50", lead: "We need a little more information to say whether the cap applies." },
};

export function VerdictCard({ r, letterHref }: { r: CheckResponse; letterHref?: string }) {
  const v = VERDICT[r.verdict];
  return (
    <section className={`space-y-3 rounded-xl border p-4 ${v.tone}`} aria-live="polite">
      <div>
        <h2 className="text-xl font-bold">{v.title}</h2>
        <p className="text-sm">{v.lead}</p>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-slate-600">Your increase</dt><dd className="text-lg font-semibold tabular-nums">{pct(r.increase_pct)}</dd></div>
        <div><dt className="text-slate-600">Cap for this date</dt><dd className="text-lg font-semibold tabular-nums">{r.cap_pct != null ? pct(r.cap_pct) : "n/a"}</dd></div>
        {r.max_legal_rent != null && <div><dt className="text-slate-600">Most your landlord can charge</dt><dd className="text-lg font-semibold tabular-nums">{usd(r.max_legal_rent, 2)}</dd></div>}
        {r.verdict === "over_cap" && r.overage_monthly != null && (
          <div><dt className="text-slate-600">Over the limit</dt><dd className="text-lg font-semibold tabular-nums">{usd(r.overage_monthly, 2)}/mo, {usd(r.overage_yearly, 2)}/yr</dd></div>
        )}
      </dl>
      {r.third_increase && <p className="text-sm font-medium">This looks like a third increase within 12 months. Ask Legal Aid how that is treated.</p>}
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {r.reasons.map((x) => <li key={x}>{x}</li>)}
      </ul>
      {letterHref && (
        <Link href={letterHref} className="inline-flex min-h-11 items-center rounded-lg bg-indigo-700 px-4 py-2 font-semibold text-on-primary">
          Get a reply letter
        </Link>
      )}
      <Disclaimer kind="legal" text={r.disclaimer} />
    </section>
  );
}

const LABEL: Record<ListingEvalResponse["label"], { title: string; tone: string }> = {
  above_typical_range: { title: "Above the typical range", tone: "text-red-800" },
  in_range: { title: "In the typical range", tone: "text-emerald-800" },
  below_typical_range: { title: "Below the typical range", tone: "text-sky-800" },
};

export function ListingCheckCard({ r }: { r: ListingEvalResponse }) {
  const { low, expected, high } = r.estimate;
  const lo = Math.min(low, r.asking_rent) * 0.95;
  const hi = Math.max(high, r.asking_rent) * 1.05;
  const at = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const l = LABEL[r.label];
  return (
    <Card className="space-y-3">
      <div>
        <h2 className={`text-xl font-bold ${l.tone}`}>{l.title}</h2>
        <p className="text-sm text-slate-700">
          Asking {usd(r.asking_rent)} against an expected {usd(expected)}
          {r.percentile != null && <>, higher than about {Math.round(r.percentile)}% of {r.n_comparables} comparable listings</>}.
        </p>
      </div>
      <div>
        <div className="relative h-8" role="img" aria-label={`Typical range ${usd(low)} to ${usd(high)}, asking rent ${usd(r.asking_rent)}`}>
          <div className="absolute top-3 h-2 w-full rounded-full bg-slate-200" />
          <div className="absolute top-3 h-2 rounded-full bg-indigo-300" style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }} />
          <div className="absolute top-2.5 h-3 w-0.5 bg-indigo-900" style={{ left: at(expected) }} />
          <div className="absolute top-0 h-8 w-1 rounded bg-amber-500" style={{ left: at(r.asking_rent) }} />
        </div>
        <div className="flex justify-between text-xs tabular-nums text-slate-600">
          <span>{usd(low)} low</span><span>{usd(expected)} expected</span><span>{usd(high)} high</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">Amber marker is the asking rent; the blue band is the 80% range.</p>
      </div>
      <p className="text-xs text-slate-600">
        {r.estimate.method === "model"
          ? `Model estimate${r.estimate.mae_usd != null ? `, typically off by about ${usd(r.estimate.mae_usd)}` : ""}${r.estimate.coverage_80 != null ? `; ${Math.round(r.estimate.coverage_80 * 100)}% of held-out rents fell inside the range` : ""}.`
          : "Based on the median for this ZIP and bedroom count, since there is not yet enough data for the model."}
      </p>
      {r.parsed_fields && Object.keys(r.parsed_fields).length > 0 && (
        <p className="text-xs text-slate-600">Read from your pasted text: {Object.entries(r.parsed_fields).map(([k, v]) => `${k} ${String(v)}`).join(", ")}.</p>
      )}
      <Disclaimer kind="estimate" text={r.disclaimer} />
    </Card>
  );
}

export function ListingAnalysisCard({ r }: { r: ListingAnalysisResponse }) {
  return (
    <Card className="space-y-4">
      <h2 className="text-xl font-bold">Listing analysis</h2>
      <div className="space-y-3">
        <Bar value={r.completeness} label="Completeness" />
        <Bar value={r.readability} label="Readability" />
        <Bar value={r.reach_score} label="Predicted reach" />
      </div>
      <div>
        <h3 className="mb-1 text-sm font-semibold">Facts your listing states</h3>
        <ul className="flex flex-wrap gap-1.5">
          {Object.entries(r.stated).map(([k, v]) => (
            <li key={k} className={`rounded-full px-2.5 py-1 text-xs ${v ? "bg-emerald-100 text-emerald-900" : "bg-slate-200 text-slate-700"}`}>
              {v ? "Stated" : "Missing"}: {k}
            </li>
          ))}
        </ul>
      </div>
      {r.gaps.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-semibold">Most comparable listings state these, yours doesn&apos;t</h3>
          <ul className="space-y-1 text-sm">
            {r.gaps.map((g) => (
              <li key={g.fact} className="flex justify-between"><span>{g.fact}</span><span className="tabular-nums text-slate-600">{Math.round(g.share_of_comparables * 100)}% of {r.n_comparables}</span></li>
            ))}
          </ul>
        </div>
      )}
      {r.explanation && <p className="text-sm text-slate-800">{r.explanation}</p>}
      <Disclaimer kind="estimate" text={r.disclaimer} />
    </Card>
  );
}
