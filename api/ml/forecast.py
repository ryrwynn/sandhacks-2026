"""12-month forecasts of ZORI and ZHVI per ZIP with an 80% band and a backtest. Owner: lane C."""


def forecast_12(series):
    """series: monthly pandas Series of dollar values with a DatetimeIndex.
    Returns a DataFrame indexed by the 12 forecast months with columns mean, pi_lower, pi_upper (dollars)."""
    raise NotImplementedError("lane C: forecast_12")


def backtest(series, horizon: int = 12) -> dict:
    """Refit with the last `horizon` months held out.
    Returns {"mape": float, "naive_mape": float, "beats_naive": bool} (percentages)."""
    raise NotImplementedError("lane C: backtest")
