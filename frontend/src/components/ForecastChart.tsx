"use client";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesResponse } from "@/lib/contract";
import { monthLabel, pct, usd } from "@/lib/format";

type Row = { month: string; actual?: number; forecast?: number; band?: [number, number] };

export default function ForecastChart({ series, title }: { series: SeriesResponse; title: string }) {
  const rows: Row[] = series.points.map((p) => (p.kind === "actual" ? { month: p.month, actual: p.value } : { month: p.month, forecast: p.value, band: p.lo80 != null && p.hi80 != null ? [p.lo80, p.hi80] : undefined }));
  // Join the dashed forecast to the last actual point.
  const lastActual = [...rows].reverse().find((r) => r.actual != null);
  if (lastActual) lastActual.forecast = lastActual.actual;
  const hasForecast = rows.some((r) => r.band);

  return (
    <figure className="space-y-2">
      <figcaption className="font-semibold">{title}</figcaption>
      <div className="h-60 w-full" role="img" aria-label={`${title}: monthly history and 12-month forecast with an 80% range`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} minTickGap={40} fontSize={11} />
            <YAxis width={52} domain={["auto", "auto"]} tickFormatter={(v: number) => (v >= 100000 ? `$${Math.round(v / 1000)}k` : `$${v}`)} fontSize={11} />
            <Tooltip
              formatter={(v: unknown, name: unknown) => [Array.isArray(v) ? `${usd(v[0] as number)} to ${usd(v[1] as number)}` : usd(v as number), name === "band" ? "80% range" : String(name)]}
              labelFormatter={(l) => monthLabel(String(l))}
            />
            <Area dataKey="band" name="band" stroke="none" fill="#6366f1" fillOpacity={0.18} isAnimationActive={false} connectNulls />
            <Line dataKey="actual" name="History" stroke="#0f172a" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="forecast" name="Forecast" stroke="#4338ca" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-slate-600">
        Solid line is history, dashed line is the forecast{hasForecast ? ", shaded area is the 80% range" : ""}.
        {series.backtest_mape != null && (
          <>
            {" "}
            Past-year test error {pct(series.backtest_mape)}
            {series.naive_mape != null && <> versus {pct(series.naive_mape)} for &quot;next year equals this month&quot;</>}
            {series.beats_naive != null && (series.beats_naive ? ": the forecast did better." : ": the forecast did not beat it, so treat it with caution.")}
          </>
        )}
      </p>
    </figure>
  );
}
