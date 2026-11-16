"""M1/M2: fair-rent method selection, and the no-write dry run. Synthetic data, no database, no network."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from api.ml import fair_rent
from api.tests.test_fair_rent import synth
from worker import train


def _canned(monkeypatch, model, median):
    monkeypatch.setattr(fair_rent, "cross_validate", lambda df, folds=5: model)
    monkeypatch.setattr(fair_rent, "fallback_cross_validate", lambda df, folds=5: median)


M = {"median_ae_usd": 150.0, "mae_usd": 200.0, "coverage_80": 0.80, "n": 1200}
B = {"median_ae_usd": 200.0, "mae_usd": 260.0, "coverage_80": 0.81, "n": 1200, "spread": {"lo_mult": 0.8, "hi_mult": 1.2}}


def test_below_min_rows_keeps_median_and_skips_model(monkeypatch):
    called = []
    monkeypatch.setattr(fair_rent, "cross_validate", lambda *a, **k: called.append(1))
    monkeypatch.setattr(fair_rent, "fallback_cross_validate", lambda df, folds=5: B)
    sel = fair_rent.select_method(synth(n=200))
    assert sel["decision"] == "zip_bed_median" and sel["model"] is None and not called
    assert "fewer than 1000" in sel["reason"]


def test_model_served_when_lower_error_and_coverage_ok(monkeypatch):
    _canned(monkeypatch, M, B)
    sel = fair_rent.select_method(synth(n=1000))
    assert sel["decision"] == "model" and sel["model"] == M and sel["median"] == B


@pytest.mark.parametrize("model,why", [
    ({**M, "median_ae_usd": 210.0}, "not lower"),
    ({**M, "median_ae_usd": 200.0}, "not lower"),
    ({**M, "coverage_80": 0.77}, "coverage"),
])
def test_median_kept_otherwise(monkeypatch, model, why):
    _canned(monkeypatch, model, B)
    sel = fair_rent.select_method(synth(n=1000))
    assert sel["decision"] == "zip_bed_median" and why in sel["reason"]


def test_coverage_boundary_is_inclusive(monkeypatch):
    _canned(monkeypatch, {**M, "coverage_80": 0.78}, B)
    assert fair_rent.select_method(synth(n=1000))["decision"] == "model"


def test_real_selection_on_synthetic_rentals_records_both():
    sel = fair_rent.select_method(synth(n=1000))
    assert sel["n"] == 1000 and sel["decision"] in ("model", "zip_bed_median")
    assert sel["model"]["median_ae_usd"] > 0 and sel["median"]["median_ae_usd"] > 0
    assert sel["reason"]


def test_recorded_metrics_keep_served_keys_and_both_methods(monkeypatch):
    _canned(monkeypatch, {**M, "coverage_80": 0.5}, B)
    m = train.fair_rent_metrics(fair_rent.select_method(synth(n=1000)))
    assert m["method"] == "zip_bed_median" and m["spread"] == B["spread"]   # the API reads spread at top level
    assert m["median_ae_usd"] == 200.0 and m["model"]["coverage_80"] == 0.5 and m["reason"]
    assert "spread" not in m["median"]


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.description, self.rows = conn, [], []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.conn.sql.append(sql)
        low = sql.lower()
        if "from areas" in low:
            self.rows = [("92101",), ("92102",), ("91901",)]   # 91901 is a "new" (county) ZIP
        elif "area_metrics" in low:
            staging = "staging_area_metrics" in low
            zips = ["91901", "92101"] if staging else ["92101", "92102"]   # 92102 is short below
            self.rows = []
            for z in zips:
                n = 20 if z == "92102" else 60
                v = 2000 * np.cumprod(1 + np.random.default_rng(int(z)).normal(0.003, 0.004, n))
                self.rows += [(z, pd.Timestamp("2020-01-01") + pd.DateOffset(months=i), float(v[i])) for i in range(n)]

    def executemany(self, *a):
        self.conn.sql.append("EXECUTEMANY")

    def fetchall(self):
        return self.rows


class FakeConn:
    read_only = False

    def __init__(self):
        self.sql = []

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_forecasts_cover_served_zips_with_36_months_and_skip_short(monkeypatch):
    monkeypatch.setattr(train, "served_zips", lambda c: {"92101", "92102", "91901"})
    rows, m = train.compute_forecasts(FakeConn(), "r", dt.datetime.now(), staging=True)
    assert {r[3] for r in rows} == {"92101", "91901"}      # 92102 has 20 months; staging adds 91901
    assert m["zips"] == 2 and m["skipped"] >= 1
    assert train.compute_forecasts(FakeConn(), "r", dt.datetime.now(), staging=False)[1]["zips"] == 1


def test_dry_run_prints_summary_and_never_writes(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(train, "load_rentals", lambda c, staging=False: synth(n=1000))
    _canned(monkeypatch, M, B)
    monkeypatch.setattr(train, "compute_scenarios", lambda *a, **k: None)
    monkeypatch.setattr(train, "record_run", lambda *a, **k: pytest.fail("dry run wrote model_runs"))
    monkeypatch.setattr(fair_rent, "save", lambda *a, **k: pytest.fail("dry run saved a model"))
    monkeypatch.setattr(train, "served_zips", lambda c: {"92101", "91901"})
    monkeypatch.setattr(train, "core_zips", lambda: {"92101"})
    out = train.dry_run(conn, staging=True)
    assert out["dry_run"] and out["rentals_used"] == 1000 and out["new_zips"] >= 1
    assert out["fair_rent"]["decision"] == "model" and out["fair_rent"]["median_method"]["coverage_80"] == 0.81
    assert out["forecasts"]["new_zips_forecast"] == 1 and out["forecasts"]["backtest_new_zips"]["series"] >= 1
    assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) or s == "EXECUTEMANY" for s in conn.sql)


def test_main_dry_run_uses_read_only_connection_and_env_staging(monkeypatch):
    import psycopg
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("RENTORKNOT_READ_STAGING", "1")
    monkeypatch.setattr("sys.argv", ["train", "--dry-run"])
    monkeypatch.setattr(psycopg, "connect", lambda url: FakeConn())
    seen = {}
    monkeypatch.setattr(train, "dry_run", lambda conn, staging: seen.update(staging=staging, ro=conn.read_only) or {"ok": 1})
    assert train.main() == 0
    assert seen == {"staging": True, "ro": True}
