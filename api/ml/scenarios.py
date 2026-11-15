"""Scenario forecasts for the API (night-forecast). Reads scenario_forecasts written by worker.train."""
from api import db
from api.ml import macro as mc

LATEST_SQL = ("SELECT run_id, made_at FROM scenario_forecasts WHERE zip = %s AND metric = %s "
              "ORDER BY made_at DESC LIMIT 1")
ROWS_SQL = ("SELECT scenario, model, month, mean_usd, lo80_usd, hi80_usd, backtest_mape, coverage_80 "
            "FROM scenario_forecasts WHERE run_id = %s AND zip = %s AND metric = %s ORDER BY scenario, month")
ACTUAL_SQL = ("SELECT period AS month, value FROM area_metrics WHERE geo_type = 'zip' AND geo_id = %s "
              "AND metric = %s AND source_key = 'zillow_research' AND period >= now() - INTERVAL '5 years' "
              "ORDER BY period")


def _num(v):
    return None if v is None else float(v)


def _pt(month, value, lo, hi, kind):
    return {"month": month, "value": float(value), "lo80": _num(lo), "hi80": _num(hi), "kind": kind}


def scenario_series(zip_: str, metric: str, scenario: str) -> dict:
    """Fields of SeriesResponse beyond zip/metric/scenario. Raises LookupError when no scenario run exists."""
    latest = db.fetch(LATEST_SQL, (zip_, metric))
    if not latest:
        raise LookupError(f"no scenario forecast for {zip_} {metric} yet")
    run_id = latest[0]["run_id"]
    rows = db.fetch(ROWS_SQL, (run_id, zip_, metric))
    actual = db.fetch(ACTUAL_SQL, (zip_, metric))
    last_actual = actual[-1]["value"] if actual else None
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["scenario"], []).append(r)
    scenarios = []
    for s in mc.SCENARIOS:
        rs = by.get(s)
        if not rs:
            continue
        pts = [_pt(r["month"], r["mean_usd"], r["lo80_usd"], r["hi80_usd"], "forecast") for r in rs]
        chg = None
        if last_actual:
            chg = round((float(rs[-1]["mean_usd"]) / float(last_actual) - 1) * 100, 1)
        scenarios.append({"scenario": s, "model": rs[0]["model"], "points": pts, "change_12m_pct": chg,
                          "backtest_mape": _num(rs[0]["backtest_mape"]), "coverage_80": _num(rs[0]["coverage_80"]),
                          "assumptions": mc.ASSUMPTIONS[s]})
    chosen = next((p for p in scenarios if p["scenario"] == scenario), None)
    if chosen is None:
        raise LookupError(f"no {scenario} forecast for {zip_} {metric}")
    points = [_pt(a["month"], a["value"], None, None, "actual") for a in actual] + chosen["points"]
    naive = ((db.forecast_run_metrics(run_id).get("by_series") or {}).get(f"{zip_}:{metric}", {})).get("naive_mape")
    return {"points": points, "scenarios": scenarios, "coverage_80": chosen["coverage_80"], "run_id": run_id,
            "backtest_mape": chosen["backtest_mape"], "naive_mape": _num(naive)}
