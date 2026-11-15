"""Scenario forecasts with macro regressors (night-forecast). Reads scenario_forecasts / macro_series."""


def scenario_series(zip_: str, metric: str, scenario: str) -> dict:
    """Return {"points": [SeriesPoint dicts: actuals + this scenario's forecast],
    "scenarios": [ScenarioPath dicts for baseline, recession, growth], "coverage_80": float | None,
    "run_id", "backtest_mape", "naive_mape"}."""
    raise NotImplementedError
