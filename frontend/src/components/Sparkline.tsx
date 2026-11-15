export default function Sparkline({ values }: { values: number[] }) {
  const W = 200, H = 44, P = 4;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [P + (i / (values.length - 1)) * (W - 2 * P), P + (1 - (v - min) / span) * (H - 2 * P)]);
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="spark" preserveAspectRatio="none" role="img" aria-label="Rent trend">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--ink)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="var(--ink)" />
    </svg>
  );
}
