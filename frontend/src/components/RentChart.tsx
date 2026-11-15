"use client";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usd } from "@/lib/format";
import { fmtMonth, type MarketRange, type MarketResponse } from "@/lib/tracker";

const RANGES: [MarketRange, string][] = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["all", "All"]];

type Row = { month: string; actual?: number; basis?: string; n?: number | null; forecast?: number; band?: [number, number] };

function rowsOf(m: MarketResponse): Row[] {
  const rows: Row[] = m.points.map((p) => ({ month: p.month, actual: p.value, basis: p.basis, n: p.n_listings }));
  const last = rows[rows.length - 1];
  if (last && m.forecast.length) last.forecast = last.actual;   // join the dashed line to the last real point
  for (const f of m.forecast) rows.push({ month: f.month, forecast: f.value, band: [f.lo80, f.hi80] });
  return rows;
}

export function RangeToggle({ value, onChange }: { value: MarketRange; onChange: (r: MarketRange) => void }) {
  return (
    <div role="group" aria-label="Date range" className="inline-flex rounded-lg bg-bg p-1">
      {RANGES.map(([r, label]) => (
        <button key={r} type="button" aria-pressed={value === r} onClick={() => onChange(r)}
          className={`min-h-11 min-w-11 rounded-md px-3 text-sm font-medium ${value === r ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(46,49,39,0.25)]" : "text-muted hover:text-ink"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

type TipProps = { active?: boolean; payload?: { payload: Row }[]; label?: string };
function Tip({ active, payload, label }: TipProps) {
  const r = active ? payload?.[0]?.payload : undefined;
  if (!r || !label) return null;
  return (
    <div className="rounded-lg bg-ink px-3 py-2 text-sm text-on-ink shadow-lg">
      <div className="font-semibold">{fmtMonth(label)}</div>
      {r.actual != null && (
        <div>{usd(r.actual)}<span className="text-on-ink/70"> {r.basis === "zori" ? "Zillow typical rent" : `median asking${r.n ? `, ${r.n} listings` : ""}`}</span></div>
      )}
      {r.band && (
        <div>Forecast {usd(r.forecast)}<span className="block text-on-ink/70">80% range {usd(r.band[0])} to {usd(r.band[1])}</span></div>
      )}
    </div>
  );
}

/** Honesty line: the backtest error, and plain words when the forecast does not beat a naive guess. */
export function BacktestNote({ mape, naive, beats }: { mape?: number | null; naive?: number | null; beats?: boolean | null }) {
  if (mape == null) return <>We could not test this forecast against past data, so treat the dashed line as a rough guess.</>;
  return (
    <>
      In a test on past data, the forecast was off by {mape.toFixed(1)}% on average
      {naive != null && <>, against {naive.toFixed(1)}% for a naive guess (&quot;next year equals today&quot;)</>}.{" "}
      {beats === false ? "It does not beat a naive guess, so use the shaded range, not the dashed line, as the takeaway." : beats === true ? "It beat the naive guess in this test, but the shaded range is still wide." : ""}
    </>
  );
}

export default function RentChart({ market, range, onRange, loading }: {
  market: MarketResponse; range: MarketRange; onRange: (r: MarketRange) => void; loading?: boolean;
}) {
  const rows = rowsOf(market);
  const last = market.points[market.points.length - 1];
  const hasForecast = market.forecast.length > 0;
  const lows = rows.flatMap((r) => [r.actual, r.band?.[0]]).filter((x): x is number => x != null);
  const highs = rows.flatMap((r) => [r.actual, r.band?.[1]]).filter((x): x is number => x != null);
  const lo = Math.floor((Math.min(...lows) - 50) / 100) * 100, hi = Math.ceil((Math.max(...highs) + 50) / 100) * 100;

  return (
    <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
      <div className="mb-2 flex justify-end"><RangeToggle value={range} onChange={onRange} /></div>
      {market.points.length === 0 ? (
        <p className="rounded-lg bg-bg p-6 text-center text-muted">There is no monthly data for this selection yet. Try &quot;All&quot; or a different area.</p>
      ) : (
        <div className="h-64 w-full sm:h-72" role="img"
          aria-label={`Monthly rent, ${hasForecast ? "with a dashed 12-month forecast and an 80% range" : "history only"}`}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 14, right: 40, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" strokeOpacity={0.45} vertical={false} />
              <XAxis dataKey="month" tickFormatter={fmtMonth} minTickGap={36} fontSize={12} stroke="var(--muted)" tickLine={false} />
              <YAxis width={56} domain={[lo, hi]} tickFormatter={(v: number) => `$${v.toLocaleString()}`} fontSize={12} stroke="var(--muted)" tickLine={false} axisLine={false} />
              <Tooltip content={<Tip />} cursor={{ stroke: "var(--ink)", strokeOpacity: 0.4 }} />
              <Area dataKey="band" stroke="var(--sage)" strokeOpacity={0.6} fill="var(--line)" fillOpacity={0.6} isAnimationActive={false} activeDot={false} />
              <Line dataKey="actual" stroke="var(--primary)" strokeWidth={2} dot={rows.length < 4 ? { r: 3, fill: "var(--primary)" } : false} activeDot={{ r: 4 }} isAnimationActive={false} />
              <Line dataKey="forecast" stroke="var(--accent-strong)" strokeWidth={2} strokeDasharray="6 4" dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
              {last && (
                <ReferenceDot x={last.month} y={last.value} r={5} fill="var(--accent)" stroke="var(--ink)" ifOverflow="extendDomain"
                  label={(p: { viewBox?: { x?: number; y?: number } }) => {
                    const x = (p.viewBox?.x ?? 0) + 8, y = (p.viewBox?.y ?? 0) - 26;
                    return (
                      <g transform={`translate(${x},${y})`}>
                        <rect width="62" height="22" rx="4" fill="var(--ink)" />
                        <text x="31" y="15" textAnchor="middle" fill="var(--on-ink)" fontSize="12" fontWeight="600">{usd(last.value)}</text>
                      </g>
                    );
                  }} />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-xs text-muted">
        USD / month · Monthly values. Solid line is history{hasForecast ? ", dashed line is the 12-month forecast, shaded area is its 80% range" : ""}.
      </p>
      <p className="mt-1 text-sm text-ink">
        {hasForecast && <BacktestNote mape={market.backtest_mape} naive={market.naive_mape} beats={market.beats_naive} />}
        {!hasForecast && "No forecast is available for this selection."}
      </p>
    </div>
  );
}
