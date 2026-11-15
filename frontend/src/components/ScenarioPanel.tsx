"use client";
import { useEffect, useState } from "react";
import ForecastChart from "./ForecastChart";
import { Card, ErrorNote, MockFlag } from "./ui";
import { errorMessage, isMock } from "@/lib/api";
import type { Metric, SeriesResponse } from "@/lib/contract";
import { pct } from "@/lib/format";
import { getZipSeriesScenarios } from "@/lib/night-api";
import type { Scenario, ScenarioPath, SeriesScenarioResponse } from "@/lib/night-types";

const NAME: Record<Scenario, string> = { baseline: "Baseline", recession: "Recession", growth: "Growth" };
type View = Scenario | "compare";

const asSeries = (s: SeriesScenarioResponse, path: ScenarioPath): SeriesResponse =>
  ({
    zip: s.zip, metric: s.metric,
    points: [...s.points.filter((p) => p.kind === "actual"), ...path.points],
    backtest_mape: path.backtest_mape ?? s.backtest_mape, naive_mape: s.naive_mape, beats_naive: s.beats_naive,
  }) as SeriesResponse;

/** Forecast with a scenario toggle. One scenario at a time, or all three side by side; each scenario has its own cone. */
export default function ScenarioPanel({ zip, metric = "zori", title }: { zip: string; metric?: Metric; title?: string }) {
  const [data, setData] = useState<SeriesScenarioResponse | null>(null);
  const [view, setView] = useState<View>("baseline");
  const [err, setErr] = useState("");
  const [mock, setMock] = useState(false);

  useEffect(() => {
    let off = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null);
    getZipSeriesScenarios(zip, metric)
      .then((r) => { if (!off) { setData(r); setMock(isMock(r)); setErr(""); } })
      .catch((e) => { if (!off) setErr(errorMessage(e)); });
    return () => { off = true; };
  }, [zip, metric]);

  if (err) return <ErrorNote>{err}</ErrorNote>;
  if (!data) return <div className="skeleton h-72" aria-label="Loading forecast" />;

  const paths = data.scenarios;
  const shown = view === "compare" ? paths : paths.filter((p) => p.scenario === view);
  const label = title ?? (metric === "zori" ? "Typical rent" : "Typical home value");

  return (
    <Card className="space-y-3">
      <MockFlag on={mock} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">{label}: scenarios</h2>
        <div role="radiogroup" aria-label="Scenario" className="flex flex-wrap gap-1 rounded-xl bg-bg p-1">
          {([...paths.map((p) => p.scenario), "compare"] as View[]).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={view === v}
              onClick={() => setView(v)}
              className={`min-h-11 rounded-lg px-3 text-sm font-medium ${view === v ? "bg-surface font-semibold text-ink shadow-sm" : "text-muted hover:text-ink"}`}
            >
              {v === "compare" ? "Compare all" : NAME[v]}
            </button>
          ))}
        </div>
      </div>
      {paths.length === 0 ? (
        <p className="text-sm text-muted">No scenario forecasts are available for this ZIP yet.</p>
      ) : (
        <div className={view === "compare" ? "grid gap-4 lg:grid-cols-3" : ""}>
          {shown.map((p) => (
            <div key={p.scenario} className="min-w-0 space-y-2">
              <ForecastChart series={asSeries(data, p)} title={`${NAME[p.scenario]}${p.change_12m_pct != null ? `: ${pct(p.change_12m_pct, 1, true)} in 12 months` : ""}`} />
              {p.assumptions.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{p.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              )}
              {p.coverage_80 != null && (
                <p className="text-xs text-muted">In past tests, {pct(p.coverage_80 * (p.coverage_80 <= 1 ? 100 : 1), 0)} of actual values fell inside this 80% range.</p>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-muted">
        Scenarios change the economic assumptions behind the forecast (for example unemployment), and the shaded range widens with them. They are what-ifs, not predictions.
      </p>
    </Card>
  );
}
