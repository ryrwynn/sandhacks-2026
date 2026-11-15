"use client";
import { useState } from "react";
import type { MarketPoint } from "@/src/lib/types";

const RANGES = [["1M", 1], ["3M", 3], ["6M", 6], ["1Y", 12], ["All", 99]] as const;
const usd = (n: number) => "$" + n.toLocaleString();

export default function RentChart({ series }: { series: MarketPoint[] }) {
  const [range, setRange] = useState<number>(12);
  const [hover, setHover] = useState<number | null>(null);
  // A line needs two points, so the 1M view shows the last two months.
  const data = series.slice(-Math.max(range, 2));

  const W = 800, H = 300, L = 52, R = 28, T = 16, B = 32;
  const lo = Math.floor((Math.min(...data.map((d) => d.median)) - 40) / 100) * 100;
  const hi = Math.ceil((Math.max(...data.map((d) => d.median)) + 40) / 100) * 100;
  const x = (i: number) => L + (i / (data.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) / 4) * i);
  const active = hover ?? data.length - 1;
  const pt = data[active];

  return (
    <div>
      <div className="seg" role="tablist" aria-label="Date range">
        {RANGES.map(([label, n]) => (
          <button key={label} role="tab" aria-selected={range === n} className={range === n ? "on" : ""} onClick={() => { setRange(n); setHover(null); }}>{label}</button>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Median asking rent over time"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          setHover(Math.min(data.length - 1, Math.max(0, Math.round(((px - L) / (W - L - R)) * (data.length - 1)))));
        }}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" className="tick">{usd(t)}</text>
          </g>
        ))}
        {data.map((d, i) => (
          <text key={d.month + i} x={x(i)} y={H - 10} textAnchor="middle" className="tick">{d.month}</text>
        ))}
        <path d={`M${x(0)},${y(lo)} ` + data.map((d, i) => `L${x(i)},${y(d.median)}`).join(" ") + ` L${x(data.length - 1)},${y(lo)} Z`} fill="var(--ink)" opacity="0.05" />
        <polyline points={data.map((d, i) => `${x(i)},${y(d.median)}`).join(" ")} fill="none" stroke="var(--ink)" strokeWidth="1.75" />
        <line x1={x(active)} x2={x(active)} y1={T} y2={H - B} stroke="var(--ink)" />
        <circle cx={x(active)} cy={y(pt.median)} r="3.5" fill="var(--ink)" />
        <g transform={`translate(${Math.min(x(active) + 8, W - 70)},${y(pt.median) - 12})`}>
          <rect width="62" height="22" rx="3" fill="var(--ink)" />
          <text x="31" y="15" textAnchor="middle" fill="#fff" fontSize="12">{usd(pt.median)}</text>
        </g>
      </svg>
      <p className="muted chart-foot">USD / month · Monthly medians</p>
    </div>
  );
}
