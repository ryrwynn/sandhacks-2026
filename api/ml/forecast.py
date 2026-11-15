"""12-month forecasts of ZORI and ZHVI per ZIP with an 80% band and a backtest. Owner: lane C."""
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

MIN_MONTHS = 36


def _clean(series) -> pd.Series:
    s = pd.Series(series).astype(float).dropna()
    s = s[s > 0]
    if len(s) < MIN_MONTHS:
        raise ValueError(f"need at least {MIN_MONTHS} monthly values, got {len(s)}")
    return s


def _ets_forecast(s: pd.Series, steps: int) -> pd.DataFrame:
    """ETS on log values, additive damped trend (ZORI/ZHVI are seasonally adjusted)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ETSModel(np.log(s.reset_index(drop=True)), error="add", trend="add",
                       damped_trend=True).fit(disp=False)
        frame = fit.get_prediction(start=len(s), end=len(s) + steps - 1).summary_frame(alpha=0.2)
    return np.exp(frame[["mean", "pi_lower", "pi_upper"]]).reset_index(drop=True)


def forecast_12(series):
    """series: monthly pandas Series of dollar values with a DatetimeIndex.
    Returns a DataFrame indexed by the 12 forecast months with columns mean, pi_lower, pi_upper (dollars)."""
    s = _clean(series)
    out = _ets_forecast(s, 12)
    if isinstance(s.index, pd.DatetimeIndex):
        last = s.index[-1]
        out.index = pd.date_range(last, periods=13, freq="MS" if last.day == 1 else "ME")[1:]
    return out


def backtest(series, horizon: int = 12) -> dict:
    """Refit with the last `horizon` months held out.
    Returns {"mape": float, "naive_mape": float, "beats_naive": bool} (percentages)."""
    s = _clean(series)
    train, actual = s.iloc[:-horizon], s.iloc[-horizon:].to_numpy()
    if len(train) < MIN_MONTHS - 12:
        raise ValueError("series too short to backtest")
    pred = _ets_forecast(train, horizon)["mean"].to_numpy()
    mape = float(np.mean(np.abs(pred - actual) / actual) * 100)
    naive = float(np.mean(np.abs(train.iloc[-1] - actual) / actual) * 100)
    return {"mape": mape, "naive_mape": naive, "beats_naive": bool(mape < naive)}
