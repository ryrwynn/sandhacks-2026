"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Delta } from "./ApartmentCard";
import { BacktestNote } from "./RentChart";
import { cardCls } from "./styles";
import PropertyIcon from "./PropertyIcon";
import { ErrorNote, MockFlag } from "./ui";
import { ListingTrends } from "./Trends";
import { errorMessage, getListing, isMock } from "@/lib/api";
import { usd } from "@/lib/format";
import { useSaved } from "@/lib/saved";
import { AMENITY_TEXT, bedsText, FAIR_LABEL, FB_BADGE, fmtDate, isFacebook, listingTitle, UNIT_TYPE_TEXT, type ListingDetail, type Observation } from "@/lib/tracker";

type Kind = "Listed" | "Price change" | "Removed" | "Seen" | "Reposted";
type Ev = { t: number; date: string; price: number; kind: Kind; diff: number };

/** Label each real observation. Nothing is added: a "Seen" row is a scrape that saw the same price again. */
function events(obs: Observation[]): Ev[] {
  return obs.map((o, i) => {
    const prev = i > 0 ? obs[i - 1].price_usd : o.price_usd;
    const kind: Kind = o.event === "removed" ? "Removed" : i === 0 ? "Listed" : o.event === "posted" ? (o.price_usd !== prev ? "Price change" : "Reposted") : o.price_usd !== prev ? "Price change" : "Seen";
    return { t: new Date(o.date + "T00:00:00Z").getTime(), date: o.date, price: o.price_usd, kind, diff: o.price_usd - prev };
  });
}

const MARK: Record<Kind, { fill: string; label: string }> = {
  Listed: { fill: "var(--primary)", label: "circle" },
  "Price change": { fill: "var(--accent-strong)", label: "diamond" },
  Removed: { fill: "var(--warn)", label: "square" },
  Seen: { fill: "var(--grid)", label: "dot" },
  Reposted: { fill: "var(--grid)", label: "dot" },
};

function Marker({ cx, cy, payload }: { cx?: number; cy?: number; payload?: Ev }) {
  if (cx == null || cy == null || !payload) return <g />;
  const { kind } = payload;
  const f = MARK[kind].fill;
  if (kind === "Seen" || kind === "Reposted") return <circle cx={cx} cy={cy} r={2.5} fill={f} />;
  if (kind === "Price change") return <rect x={cx - 5} y={cy - 5} width={10} height={10} fill={f} stroke="var(--surface)" strokeWidth={1.5} transform={`rotate(45 ${cx} ${cy})`} />;
  if (kind === "Removed") return <rect x={cx - 5} y={cy - 5} width={10} height={10} fill={f} stroke="var(--surface)" strokeWidth={1.5} />;
  return <circle cx={cx} cy={cy} r={6} fill={f} stroke="var(--surface)" strokeWidth={1.5} />;
}

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Ev }[] }) {
  const e = active ? payload?.[0]?.payload : undefined;
  if (!e) return null;
  return (
    <div className="rounded-lg bg-ink px-3 py-2 text-sm text-on-ink shadow-lg">
      <div className="font-semibold">{fmtDate(e.date)}</div>
      <div>{usd(e.price)} <span className="text-on-ink/70">{e.kind}</span></div>
    </div>
  );
}

function Section({ title, children, id }: { title: string; children: React.ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className={`${cardCls} space-y-3 p-4 sm:p-6`}>
      <h2 id={id} className="text-xl font-bold">{title}</h2>
      {children}
    </section>
  );
}

function RangeBar({ low, high, value, expected }: { low: number; high: number; value: number; expected: number }) {
  const lo = Math.min(low, value), hi = Math.max(high, value);
  const pos = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  return (
    <div className="px-2 pb-6 pt-8" role="img" aria-label={`Typical range ${usd(low)} to ${usd(high)}, expected ${usd(expected)}, this apartment ${usd(value)}`}>
      <div className="relative h-3 rounded-full bg-bg">
        <div className="absolute h-3 rounded-full bg-line" style={{ left: pos(low), width: `calc(${pos(high)} - ${pos(low)})` }} />
        <div className="absolute top-0 h-3 w-0.5 bg-sage" style={{ left: pos(expected) }} />
        <div className="absolute -top-6 -translate-x-1/2 whitespace-nowrap text-xs font-semibold" style={{ left: pos(value) }}>This one</div>
        <div className="absolute -top-1 h-5 w-5 -translate-x-1/2 rounded-full border-2 border-surface bg-accent-strong" style={{ left: pos(value) }} />
        <div className="absolute top-5 text-xs text-muted" style={{ left: pos(low) }}>{usd(low)}</div>
        <div className="absolute right-0 top-5 text-xs text-muted" style={{ left: "auto" }}>{usd(high)}</div>
      </div>
    </div>
  );
}

export default function ApartmentView({ id }: { id: string }) {
  const n = Number(id);
  const [d, setD] = useState<ListingDetail | null>(null);
  const [err, setErr] = useState("");
  const { has, toggle } = useSaved();

  useEffect(() => {
    if (!Number.isInteger(n)) { setErr("That apartment link is not valid."); return; }
    let cancelled = false;
    getListing(n).then((x) => { if (!cancelled) setD(x); }).catch((e) => { if (!cancelled) setErr(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [n]);

  if (err) return <main className="space-y-3"><h1 className="text-xl font-bold">Apartment</h1><ErrorNote>{err}</ErrorNote><Link href="/find" className="font-semibold underline">Find apartments</Link></main>;
  if (!d) return <main className="space-y-4"><h1 className="sr-only">Apartment</h1><div className="skeleton h-28" /><div className="skeleton h-80" /><div className="skeleton h-40" /></main>;

  const ev = events(d.observations);
  const isRent = d.listing_type === "rent";
  const fb = isFacebook(d);
  const title = listingTitle(d);
  const facts = [
    d.neighborhood ? `${d.neighborhood}${d.zip ? ` (${d.zip})` : ""}` : d.zip,
    bedsText(d.beds),
    d.baths != null ? `${d.baths} bath` : null,
    d.sqft ? `${d.sqft.toLocaleString()} sq ft` : null,
    fb && d.unit_type ? UNIT_TYPE_TEXT[d.unit_type] : null,
    d.property_type ? d.property_type.replace("_", " ") : null,
    d.year_built ? `built ${d.year_built}` : null,
    d.available_date ? `available ${fmtDate(d.available_date, { month: "short", day: "numeric" })}` : null,
  ].filter(Boolean);
  const amenities = (d.amenities ?? []).map((a) => AMENITY_TEXT[a] ?? a);
  const rentCheck = `/renter?${new URLSearchParams({ ...(d.address ? { address: d.address + (d.unit_label ? ` ${d.unit_label}` : "") } : {}), ...(d.year_built ? { year_built: String(d.year_built) } : {}), ...(d.zip ? { zip: d.zip } : {}) }).toString()}`;
  const f = d.forecast;
  const e = d.estimate;
  const prices = ev.map((x) => x.price);
  const pad = 50;

  return (
    <main className="space-y-5">
      <MockFlag on={isMock(d)} />
      <header className={`${cardCls} flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-6`}>
        <div className="min-w-0">
          <Link href="/find" className="mb-2 inline-flex min-h-11 items-center text-sm font-medium text-accent-strong underline underline-offset-2">← Find apartments</Link>
          {fb && (
            <p className="mb-2 text-sm text-muted">
              <span className="mr-1.5 inline-block rounded-full bg-line px-2.5 py-0.5 text-xs font-medium text-ink">{FB_BADGE}</span>
              {d.group_name}
            </p>
          )}
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl">{title}</h1>
          <p className="flex items-center gap-1.5 text-muted">{d.property_type && <PropertyIcon type={d.property_type} size={20} />}<span className="min-w-0">{facts.join(" · ")}</span></p>
          <p className="mt-3">
            <strong className="text-2xl font-bold tabular-nums">{usd(d.current_price_usd)}</strong>
            <span className="text-muted">{isRent ? " / mo" : " asking price"}</span>
            {d.n_observations > 1 && <span className="ml-3 inline-block align-middle"><Delta now={d.current_price_usd} then={d.first_price_usd} suffix={`since ${fmtDate(d.first_observed)}`} /></span>}
          </p>
          {fb && (
            <p className="mt-1 text-sm text-muted">
              {d.posted_at && <>Posted {fmtDate(d.posted_at)} · </>}Tracking since {fmtDate(d.first_observed)}
              {amenities.length > 0 && <> · {amenities.join(", ")}</>}
            </p>
          )}
          {d.unusual_price && (
            <p className="mt-1 text-sm text-warn">Unusual price: far from what listing sites ask for {bedsText(d.beds)?.toLowerCase() ?? "this size"} in {d.zip}. Check the post before relying on it; it is left out of our medians.</p>
          )}
          {!d.active && <p className="mt-1 text-sm text-warn">{fb ? "Not reposted in the last 21 days." : "Not seen in our latest update."} It may no longer be available.</p>}
        </div>
        <div className="flex flex-col gap-2 sm:items-end">
          <button type="button" aria-pressed={has(d.id)} onClick={() => toggle(d)}
            className={`min-h-11 rounded-lg px-5 font-semibold ${has(d.id) ? "bg-line text-ink" : "bg-primary text-on-primary hover:bg-primary-hover"}`}>
            {has(d.id) ? "Saved ✓" : "+ Save apartment"}
          </button>
          {fb && d.post_url && (
            <a href={d.post_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center rounded-lg px-3 font-medium text-accent-strong underline underline-offset-2">View post on Facebook ↗</a>
          )}
          {d.source_url && (
            <a href={d.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center rounded-lg px-3 font-medium text-accent-strong underline underline-offset-2">View original listing ↗</a>
          )}
        </div>
      </header>

      <Section id="hist-h" title="Asking price history">
        {ev.length < 2 ? (
          <p className="text-muted">We have one price so far: {usd(ev[0]?.price)} on {fmtDate(ev[0]?.date)}. The chart appears after the price is seen again.</p>
        ) : (
          <div className="h-64 w-full sm:h-72" role="img" aria-label={`Asking price steps from ${usd(ev[0].price)} to ${usd(ev[ev.length - 1].price)} across ${ev.length} observations`}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={ev} margin={{ top: 12, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="var(--grid)" strokeOpacity={0.45} vertical={false} />
                <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => fmtDate(new Date(t).toISOString().slice(0, 10), { month: "short", year: "2-digit" })} fontSize={12} stroke="var(--muted)" tickLine={false} />
                <YAxis width={56} domain={[Math.floor((Math.min(...prices) - pad) / 50) * 50, Math.ceil((Math.max(...prices) + pad) / 50) * 50]} tickFormatter={(v: number) => `$${v.toLocaleString()}`} fontSize={12} stroke="var(--muted)" tickLine={false} axisLine={false} />
                <Tooltip content={<Tip />} />
                <Line dataKey="price" type="stepAfter" stroke="var(--primary)" strokeWidth={2} dot={<Marker />} activeDot={{ r: 7 }} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted" aria-label="Chart key">
          <li><span className="mr-1 inline-block h-3 w-3 rounded-full bg-primary align-middle" />Listed</li>
          <li><span className="mr-1 inline-block h-2.5 w-2.5 rotate-45 bg-accent-strong align-middle" />Price change</li>
          <li><span className="mr-1 inline-block h-2.5 w-2.5 bg-warn align-middle" />Removed</li>
          <li><span className="mr-1 inline-block h-2 w-2 rounded-full bg-grid align-middle" />{fb ? "Reposted at the same price" : "Seen again at the same price"}</li>
        </ul>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Every recorded price event for this apartment</caption>
            <thead className="text-muted"><tr><th className="py-2 pr-3 font-medium">Date</th><th className="py-2 pr-3 font-medium">Event</th><th className="py-2 pr-3 text-right font-medium">Price</th><th className="py-2 text-right font-medium">Change</th></tr></thead>
            <tbody>
              {[...ev].reverse().map((x, i) => (
                <tr key={`${x.date}-${i}`} className="border-t border-line">
                  <td className="py-2 pr-3">{fmtDate(x.date)}</td>
                  <td className="py-2 pr-3">{x.kind}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{usd(x.price)}</td>
                  <td className={`py-2 text-right tabular-nums ${x.diff < 0 ? "text-good" : x.diff > 0 ? "text-warn" : "text-muted"}`}>
                    {x.diff === 0 ? "–" : <><span aria-hidden="true">{x.diff < 0 ? "↓" : "↑"} {usd(Math.abs(x.diff))}</span><span className="sr-only">{x.diff < 0 ? "down" : "up"} {usd(Math.abs(x.diff))}</span></>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {isRent && (
        <Section id="fair-h" title="What it should rent for">
          {e ? (
            <>
              <p className="text-lg">
                Around <strong className="tabular-nums">{usd(e.expected)}</strong> a month, typically between <strong className="tabular-nums">{usd(e.low)}</strong> and <strong className="tabular-nums">{usd(e.high)}</strong>.
                {d.fair_rent_label && <span className="ml-2 inline-block rounded-full bg-bg px-2.5 py-1 align-middle text-sm font-medium">{FAIR_LABEL[d.fair_rent_label]}</span>}
              </p>
              <RangeBar low={e.low} high={e.high} value={d.current_price_usd} expected={e.expected} />
              {d.percentile != null && (
                <p>
                  At {usd(d.current_price_usd)}, this is at the {Math.round(d.percentile)}th percentile of {d.n_comparables} comparable listings{d.zip ? ` in ${d.zip}` : ""} with the same number of bedrooms: about {Math.round(d.percentile)}% of them ask less.
                </p>
              )}
              <p className="text-sm text-muted">
                {fb && "From the ZIP and bedroom count only, since the post gives no address. "}
                {e.method === "model" ? "Estimated by a model trained on listings" : "The median of comparable listings"}
                {e.mae_usd != null && <>; it is typically off by about {usd(e.mae_usd)}</>}. {d.disclaimer}
              </p>
            </>
          ) : (
            <p className="text-muted">{fb && d.unit_type !== "entire_unit" ? "Rooms and sublets aren't compared with whole-unit rents, so there is no estimate for this one." : "There are not enough comparable listings yet to estimate a typical rent for this apartment."}</p>
          )}
        </Section>
      )}

      {f && (
        <Section id="hood-h" title={`Neighborhood: ${f.name}`}>
          {f.change_pct != null && f.forecast_12m_usd != null ? (
            <>
              <p>
                Typical {f.metric === "zori" ? "rent" : "home value"} in {f.zip} is {usd(f.latest_usd)}. The 12-month forecast is{" "}
                <strong className="tabular-nums">{usd(f.forecast_12m_usd)}</strong> ({f.change_pct > 0 ? "up" : f.change_pct < 0 ? "down" : "no change"} {Math.abs(f.change_pct).toFixed(1)}%)
                {f.lo80_usd != null && f.hi80_usd != null && <>, with an 80% range of {usd(f.lo80_usd)} to {usd(f.hi80_usd)}</>}.
              </p>
              <p className="text-sm text-muted"><BacktestNote mape={f.backtest_mape} naive={f.naive_mape} beats={f.beats_naive} /></p>
            </>
          ) : (
            <p className="text-muted">No forecast is available for this ZIP.</p>
          )}
          <Link href={`/zip/${f.zip}`} className="inline-flex min-h-11 items-center font-semibold text-accent-strong underline underline-offset-2">See the {f.name} profile →</Link>
        </Section>
      )}

      <Section id="trend-h" title="Price trends"><ListingTrends id={d.id} /></Section>

      {isRent && !fb && (
        <Section id="own-h" title="Renting here already?">
          <p className="text-muted">If you already live in this building and got a rent increase notice, check it against California&apos;s AB 1482 cap.</p>
          <Link href={rentCheck} className="inline-flex min-h-11 items-center rounded-lg bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover">Check a rent increase</Link>
        </Section>
      )}
    </main>
  );
}
