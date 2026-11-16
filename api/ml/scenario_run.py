"""Run the scenario backtest and forecasts for all series and shape the results (night-forecast).

Used by worker/train.py (writes scenario_forecasts) and by `python -m api.ml.scenario_run` (prints the
MODEL_CARD tables from the committed Zillow extracts and macro snapshot, no database needed).
"""
import numpy as np
import pandas as pd

from api.ml import macro as mc
from api.ml import scenario_model as sm
from api.ml.forecast import forecast_12

METHODS = ("naive", "ets", "baseline", "recession", "growth", "oracle", "own")


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 3)


def run_metric(panel: pd.DataFrame, macro_frame: pd.DataFrame, fed: dict | None = None, with_ets: bool = True,
               min_origin: int = sm.MIN_ORIGIN) -> dict:
    """Backtest + forecast one metric. Returns {"by_series": {zip: {...}}, "forecast": {...}, "selected": str,
    "summary": {...}}."""
    bt = sm.backtest(panel, macro_frame, fed, with_ets=with_ets, min_origin=min_origin)
    ev = sm.evaluate(bt)
    fc = sm.forecast_all(panel, macro_frame, bt, fed)
    m = ev["methods"]
    by = {}
    for z, zip_ in enumerate(ev["zips"]):
        row = {}
        for name in METHODS:
            if name in m:
                row[f"{name}_mape"] = _f(m[name]["mape"][z])
                if "coverage" in m[name]:
                    row[f"{name}_coverage"] = _f(m[name]["coverage"][z])
        by[zip_] = row
    mean = {n: float(np.mean(m[n]["mape"])) for n in m}
    selected = "pooled_x"
    if with_ets and mean["ets"] < mean["baseline"]:
        selected = "ets"
    summary = {n: {"mape": _f(mean[n]), "coverage": _f(m[n].get("coverage_all"))} for n in m}
    summary["n_test_origins"] = int(len(ev["test"]))
    summary["selected_baseline"] = selected
    return {"by_series": by, "forecast": fc, "selected": selected, "summary": summary, "panel": panel, "bt": bt}


def _ets_baseline(panel: pd.DataFrame) -> dict:
    out = {"mean": [], "lo": [], "hi": []}
    for z in panel.columns:
        f = forecast_12(panel[z])
        out["mean"].append(f["mean"].to_numpy()); out["lo"].append(f["pi_lower"].to_numpy())
        out["hi"].append(f["pi_upper"].to_numpy())
    return {k: np.array(v).T for k, v in out.items()}


def forecast_rows(metric: str, res: dict, run_id: str, made_at, zips: set[str] | None = None) -> list[tuple]:
    """Rows for scenario_forecasts: (run_id, made_at, scenario, model, month, zip, metric, mean, lo, hi, mape, cov)."""
    panel, fc = res["panel"], res["forecast"]
    ets = _ets_baseline(panel) if res["selected"] == "ets" else None
    rows = []
    for s in mc.SCENARIOS:
        d = fc[s]
        model = "ets" if (s == "baseline" and ets) else "pooled_x"
        for zi, z in enumerate(panel.columns):
            if zips is not None and z not in zips:
                continue
            by = res["by_series"][z]
            mp = by.get("ets_mape" if model == "ets" else f"{s}_mape")
            cv = by.get("ets_coverage" if model == "ets" else f"{s}_coverage")
            src = ets if model == "ets" else d
            for h, month in enumerate(d["months"]):
                rows.append((run_id, made_at, s, model, month.date(), z, metric, round(float(src["mean"][h, zi]), 2),
                             round(float(src["lo"][h, zi]), 2), round(float(src["hi"][h, zi]), 2), mp, cv))
    return rows


def card_tables(results: dict[str, dict]) -> str:
    """Markdown tables of backtest MAPE and coverage per series, for docs/MODEL_CARD.md."""
    out = []
    for metric, res in results.items():
        out.append(f"\n#### {metric.upper()} per ZIP (held-out origins; MAPE %, then 80% coverage)\n")
        out.append("| ZIP | naive | ETS | baseline | recession | growth | oracle | baseline cov | ETS cov | recession cov | growth cov |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        g = lambda r, k: "" if r.get(k) is None else f"{r[k]:.2f}"
        for z, r in res["by_series"].items():
            out.append(f"| {z} | {g(r,'naive_mape')} | {g(r,'ets_mape')} | {g(r,'baseline_mape')} | {g(r,'recession_mape')} | "
                       f"{g(r,'growth_mape')} | {g(r,'oracle_mape')} | {g(r,'baseline_coverage')} | {g(r,'ets_coverage')} | "
                       f"{g(r,'recession_coverage')} | {g(r,'growth_coverage')} |")
        s = res["summary"]
        out.append(f"| **all** | {s['naive']['mape']} | {s.get('ets',{}).get('mape','')} | {s['baseline']['mape']} | "
                   f"{s['recession']['mape']} | {s['growth']['mape']} | {s['oracle']['mape']} | {s['baseline']['coverage']} | "
                   f"{s.get('ets',{}).get('coverage','')} | {s['recession']['coverage']} | {s['growth']['coverage']} |")
        out.append(f"\nTest origins: {s['n_test_origins']}. Baseline served from: {res['selected']}.")
    return "\n".join(out)


def main() -> None:
    macro_frame = mc.to_model_frame(mc.load_snapshot())
    results = {m: run_metric(sm.load_panel_csv(m), macro_frame) for m in ("zori", "zhvi")}
    print(card_tables(results))


if __name__ == "__main__":
    main()
