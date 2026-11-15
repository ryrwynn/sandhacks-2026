import type { SparkPoint } from "@/lib/tracker";

/** A line through real monthly observations, spaced by date. One observation draws a dot, never a made-up line. */
export default function Sparkline({ points, label }: { points: SparkPoint[]; label?: string }) {
  const W = 200, H = 44, P = 5;
  if (points.length === 0) return null;
  const vals = points.map((p) => p.price_usd);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const t = points.map((p) => new Date(p.month).getTime());
  const t0 = t[0], tSpan = t[t.length - 1] - t0 || 1;
  const xy = points.map((p, i) => [
    points.length === 1 ? W / 2 : P + ((t[i] - t0) / tSpan) * (W - 2 * P),
    max === min ? H / 2 : P + (1 - (p.price_usd - min) / span) * (H - 2 * P),
  ]);
  const last = xy[xy.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-11 w-full" preserveAspectRatio="none" role="img" aria-label={label ?? "Asking rent over time"}>
      {points.length > 1 && (
        <polyline points={xy.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      )}
      <circle cx={last[0]} cy={last[1]} r="3" fill="var(--accent-strong)" />
    </svg>
  );
}
