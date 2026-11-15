import numpy as np
import pandas as pd
import pytest

from api.ml.forecast import backtest, forecast_12


def make_series(n=84, seed=0, drift=0.004):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="MS")
    vals = 2000 * np.exp(np.cumsum(drift + rng.normal(0, 0.003, n)))
    return pd.Series(vals, index=idx)


def test_forecast_shape_and_band():
    s = make_series()
    f = forecast_12(s)
    assert len(f) == 12
    assert list(f.columns) == ["mean", "pi_lower", "pi_upper"]
    assert (f["pi_lower"] < f["mean"]).all() and (f["mean"] < f["pi_upper"]).all()
    assert f.index[0] == s.index[-1] + pd.offsets.MonthBegin(1)
    assert f["mean"].iloc[-1] > s.iloc[-1]  # trending series keeps trending


def test_backtest_trending_series_beats_naive():
    b = backtest(make_series())
    assert set(b) == {"mape", "naive_mape", "beats_naive"}
    assert b["mape"] < 10
    assert b["beats_naive"] is True


def test_backtest_flat_series_reports_honestly():
    b = backtest(make_series(drift=0.0, seed=3))
    assert b["beats_naive"] == (b["mape"] < b["naive_mape"])


def test_short_series_rejected():
    with pytest.raises(ValueError):
        forecast_12(make_series(n=20))
