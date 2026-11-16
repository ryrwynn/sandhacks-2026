"""Scenario forecasts: macro paths, model, calibration, writer rows and the ?scenario= endpoint (mocked DB)."""
from datetime import date, datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import db
from api.main import app
from api.ml import macro as mc
from api.ml import scenario_model as sm
from api.ml import scenario_run, scenarios

client = TestClient(app)
_ORIG_RUN = scenario_run.run_metric


@pytest.fixture(scope="module")
def macro_frame():
    return mc.to_model_frame(mc.load_snapshot())


def test_fed_tables_complete_and_ordered():
    fed = mc.load_fed()
    for s in ("baseline", "recession"):
        for k in ("unemployment", "mortgage_rate", "house_price_index"):
            assert len(fed[s][k]) == 13
    assert max(fed["recession"]["unemployment"]) == 10.0          # Fed severely adverse peak
    assert fed["recession"]["house_price_index"][7] / fed["baseline"]["house_price_index"][0] < 0.72


def test_scenario_deltas_ordering(macro_frame):
    d = mc.scenario_deltas(macro_frame)
    assert set(d) == {"baseline", "recession", "growth"}
    assert all(v.shape == (12, 3) for v in d.values())
    assert d["recession"][-1, 0] > d["baseline"][-1, 0] > d["growth"][-1, 0] - 1e-9   # unemployment
    assert d["recession"][-1, 1] < d["baseline"][-1, 1] < d["growth"][-1, 1]          # log house prices
    lv = mc.scenario_levels(macro_frame, d["recession"])
    assert len(lv) == 12 and lv["ur"].iloc[-1] > macro_frame["ur"].iloc[-1]


def test_growth_path_comes_from_history(macro_frame):
    d12 = (macro_frame - macro_frame.shift(12)).dropna()
    g = mc.growth_deltas(macro_frame)
    assert g[-1, 1] == pytest.approx(d12["lhpi"].quantile(0.8))
    assert g[-1, 0] == pytest.approx(d12["ur"].quantile(0.2))


def synthetic_panel(n=110, zips=6, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2017-01-01", periods=n, freq="MS")
    cols = {f"9{i:04d}": 2000 * np.exp(np.cumsum(0.003 + rng.normal(0, 0.003, n))) for i in range(zips)}
    return pd.DataFrame(cols, index=idx)


def test_backtest_and_calibration_shapes(macro_frame):
    panel = synthetic_panel()
    mf = macro_frame.reindex(pd.date_range("2000-01-01", "2026-10-01", freq="MS")).ffill()
    bt = sm.backtest(panel, mf, with_ets=False)
    O, Z = len(bt["origins"]), panel.shape[1]
    assert bt["actual"].shape == (O, 12, Z)
    ev = sm.evaluate(bt)
    b = ev["methods"]["baseline"]
    assert b["mape"].shape == (Z,) and np.all(b["mape"] > 0)
    assert 0.5 < b["coverage_all"] <= 1.0
    # a hard recession shock is much worse than the baseline when nothing like it happens
    assert ev["methods"]["recession"]["mape"].mean() > b["mape"].mean()


def test_forecast_all_scenario_order_and_cone(macro_frame):
    panel = synthetic_panel()
    mf = macro_frame.reindex(pd.date_range("2000-01-01", "2026-10-01", freq="MS")).ffill()
    bt = sm.backtest(panel, mf, with_ets=False)
    fc = sm.forecast_all(panel, mf, bt)
    assert set(fc) == {"baseline", "recession", "growth"}
    for s in fc.values():
        assert np.all(s["lo"] < s["mean"]) and np.all(s["mean"] < s["hi"])
    assert fc["baseline"]["months"][0] == panel.index[-1] + pd.offsets.MonthBegin(1)
    assert np.mean(fc["recession"]["mean"][-1]) < np.mean(fc["growth"]["mean"][-1])


def test_forecast_rows_only_for_requested_zips(macro_frame):
    panel = synthetic_panel(zips=4)
    mf = macro_frame.reindex(pd.date_range("2000-01-01", "2026-10-01", freq="MS")).ffill()
    res = scenario_run.run_metric(panel, mf, with_ets=False)
    keep = {panel.columns[0], panel.columns[1]}
    rows = scenario_run.forecast_rows("zori", res, "run", datetime.now(timezone.utc), keep)
    assert {r[5] for r in rows} == keep
    assert {r[2] for r in rows} == {"baseline", "recession", "growth"}
    assert len(rows) == 2 * 3 * 12
    assert all(r[9] > r[7] > r[8] > 0 for r in rows)


def test_train_scenarios_writes_core_zips_only(monkeypatch, macro_frame):
    from worker import train

    panel = synthetic_panel(zips=4)
    series = {z: panel[z] for z in panel.columns}
    monkeypatch.setattr(train, "load_series", lambda conn, metric, staging=False: series)
    monkeypatch.setattr(train, "load_macro", lambda conn: macro_frame.reindex(
        pd.date_range("2000-01-01", "2026-10-01", freq="MS")).ffill())
    monkeypatch.setattr(train.scenario_run, "run_metric", lambda p, m, **k: _ORIG_RUN(p, m, with_ets=False))
    written, runs = [], []

    class Cur:
        def executemany(self, sql, rows):
            written.append((sql, list(rows)))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            runs.append(params)

    class Conn:
        def cursor(self):
            return Cur()

    keep = set(list(series)[:2])
    m = train.train_scenarios(Conn(), __import__("uuid").uuid4(), datetime.now(timezone.utc), keep)
    assert m and "zori" in m["summary"]
    sql, rows = written[0]
    assert "scenario_forecasts" in sql
    assert {r[5] for r in rows} == keep
    assert runs and runs[0][1] == "scenario_forecast"


# ---------- endpoint with a mocked DB ----------
def _rows(scen_models):
    out = []
    for s, model in scen_models.items():
        for i in range(12):
            base = {"baseline": 2700, "recession": 2500, "growth": 2900}[s] + 5 * i
            out.append({"scenario": s, "model": model, "month": date(2026 + (10 + i) // 12, (10 + i) % 12 + 1, 1),
                        "mean_usd": Decimal(base), "lo80_usd": Decimal(base - 100), "hi80_usd": Decimal(base + 100),
                        "backtest_mape": Decimal("1.60"), "coverage_80": Decimal("0.790")})
    return out


@pytest.fixture
def mock_db(monkeypatch):
    def fetch(sql, params=None):
        if "FROM scenario_forecasts WHERE zip" in sql:
            return [{"run_id": "11111111-1111-1111-1111-111111111111", "made_at": None}]
        if "FROM scenario_forecasts WHERE run_id" in sql:
            return _rows({"baseline": "pooled_x", "recession": "pooled_x", "growth": "pooled_x"})
        if "FROM area_metrics" in sql:
            return [{"month": date(2026, 9, 1), "value": Decimal(2680)}, {"month": date(2026, 10, 1), "value": Decimal(2700)}]
        raise AssertionError(sql)
    monkeypatch.setattr(db, "fetch", fetch)
    monkeypatch.setattr(db, "forecast_run_metrics",
                        lambda rid: {"by_series": {"92104:zori": {"naive_mape": 1.2}}})


def test_series_scenario_param_returns_paths(mock_db):
    r = client.get("/zips/92104/series", params={"metric": "zori", "scenario": "recession"})
    assert r.status_code == 200
    j = r.json()
    assert j["scenario"] == "recession" and j["coverage_80"] == 0.79
    assert [s["scenario"] for s in j["scenarios"]] == ["baseline", "recession", "growth"]
    kinds = [p["kind"] for p in j["points"]]
    assert kinds[:2] == ["actual", "actual"] and kinds[-1] == "forecast"
    rec = next(s for s in j["scenarios"] if s["scenario"] == "recession")
    assert rec["change_12m_pct"] < 0 and rec["assumptions"]
    assert j["naive_mape"] == 1.2


def test_series_default_response_unchanged(monkeypatch):
    monkeypatch.setattr(db, "series", lambda z, m: [])
    r = client.get("/zips/92104/series")
    assert r.status_code == 200
    j = r.json()
    assert j["scenario"] is None and j["scenarios"] == [] and j["coverage_80"] is None


def test_series_scenario_without_run_is_404(monkeypatch):
    monkeypatch.setattr(db, "fetch", lambda *a, **k: [])
    assert client.get("/zips/92104/series", params={"scenario": "growth"}).status_code == 404


def test_series_scenario_db_down_is_503(monkeypatch):
    def boom(*a, **k):
        raise db.DBUnavailable("no db")
    monkeypatch.setattr(db, "fetch", boom)
    assert client.get("/zips/92104/series", params={"scenario": "growth"}).status_code == 503
