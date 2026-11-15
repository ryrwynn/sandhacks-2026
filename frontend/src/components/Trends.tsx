"use client";
import { useEffect, useState, type ReactNode } from "react";
import { Card, Disclaimer, ErrorNote, MockFlag } from "./ui";
import { errorMessage, isMock } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { getListingTrends, getZipTrends } from "@/lib/night-api";
import type { ListingTrendsResponse, TrendMetrics, TrendSignal, ZipTrendsResponse } from "@/lib/night-types";
import { fmtDate } from "@/lib/tracker";

function useLoad<T extends object>(load: () => Promise<T>, key: string) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let off = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null);
    load().then((r) => { if (!off) setData(r); }).catch((e) => { if (!off) setErr(errorMessage(e)); });
    return () => { off = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { data, err };
}

function Signals({ list }: { list: TrendSignal[] }) {
  if (list.length === 0) return <p className="text-sm text-muted">No unusual movement stands out.</p>;
  return (
    <ul className="space-y-1.5">
      {list.map((s) => (
        <li key={s.kind + s.label} className="rounded-lg bg-bg px-3 py-2 text-sm">
          <span className="font-semibold">{s.label}</span>
          {s.detail && <span className="block text-xs text-muted">{s.detail}</span>}
        </li>
      ))}
    </ul>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: ReactNode }) {
  return (
    <div className="rounded-xl bg-bg p-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-lg font-bold tabular-nums">{value}</dd>
      {note && <div className="text-xs text-muted">{note}</div>}
    </div>
  );
}

function MetricBlock({ title, m }: { title: string; m: TrendMetrics }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title} <span className="font-normal text-muted">(as of {fmtDate(m.as_of)}, {usd(m.latest_usd)})</span></h3>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Change, 12 months" value={pct(m.yoy_pct, 1, true)} note={m.county_percentile != null ? `Faster than ${Math.round(m.county_percentile)}% of county ZIPs` : undefined} />
        <Stat label="Last 3 months (yearly pace)" value={pct(m.momentum_3m_pct, 1, true)} />
        <Stat label="Speeding up or slowing" value={m.acceleration_pp == null ? "n/a" : `${m.acceleration_pp > 0 ? "+" : ""}${m.acceleration_pp.toFixed(1)} pts`} note="Change in 12-month growth vs 3 months ago" />
        <Stat label="Monthly swings" value={pct(m.volatility_pct, 1)} note="Typical month-to-month change" />
      </dl>
    </div>
  );
}

/** ZIP trends: growth, momentum, acceleration, volatility, and plain-language signals. */
export function ZipTrends({ zip }: { zip: string }) {
  const { data, err } = useLoad<ZipTrendsResponse>(() => getZipTrends(zip), zip);
  if (err) return <ErrorNote>{err}</ErrorNote>;
  if (!data) return <div className="skeleton h-40" aria-label="Loading trends" />;
  return (
    <Card className="space-y-4">
      <MockFlag on={isMock(data)} />
      <h2 className="text-lg font-bold">Trends in {data.zip} {data.name}</h2>
      {data.rent && <MetricBlock title="Rent" m={data.rent} />}
      {data.value && <MetricBlock title="Home value" m={data.value} />}
      <Signals list={data.signals} />
      <Disclaimer text={data.disclaimer} />
    </Card>
  );
}

const KIND: Record<string, string> = { cut: "Price cut", raise: "Price raise", relist_jump: "Back on market at a higher price" };

/** One listing's price moves against its ZIP: cuts, raises, relist jumps. */
export function ListingTrends({ id }: { id: number }) {
  const { data, err } = useLoad<ListingTrendsResponse>(() => getListingTrends(id), String(id));
  if (err) return <ErrorNote>{err}</ErrorNote>;
  if (!data) return <div className="skeleton h-32" aria-label="Loading trends" />;
  return (
    <div className="space-y-3">
      <MockFlag on={isMock(data)} />
      <h2 className="text-lg font-bold">How this price compares with its ZIP</h2>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Since first seen" value={pct(data.total_change_pct, 1, true)} note={`${usd(data.first_price_usd)} to ${usd(data.current_price_usd)}`} />
        <Stat label="ZIP typical rent, same dates" value={pct(data.zip_change_pct, 1, true)} />
        <Stat label="This listing vs the ZIP" value={data.vs_zip_pp == null ? "n/a" : `${data.vs_zip_pp > 0 ? "+" : ""}${data.vs_zip_pp.toFixed(1)} pts`} />
        <Stat label="Price observations" value={String(data.n_observations)} />
      </dl>
      {data.changes.length > 0 && (
        <ul className="divide-y divide-line rounded-lg bg-bg text-sm">
          {data.changes.map((c) => (
            <li key={c.date + c.to_usd} className="flex flex-wrap items-center justify-between gap-x-3 px-3 py-2">
              <span><span className="font-semibold">{KIND[c.kind]}</span> <span className="text-muted">{fmtDate(c.date)}{c.days_since_previous != null ? `, ${c.days_since_previous} days after the last change` : ""}</span></span>
              <span className="tabular-nums">{usd(c.from_usd)} to {usd(c.to_usd)} ({pct(c.change_pct, 1, true)})</span>
            </li>
          ))}
        </ul>
      )}
      <Signals list={data.signals} />
      <Disclaimer text={data.disclaimer} />
    </div>
  );
}
