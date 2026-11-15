"""Macro inputs and scenario paths for the scenario forecasts (night-forecast).

Series: ur = San Diego County unemployment rate, hpi = Case-Shiller San Diego home price index,
mort = 30-year mortgage rate (US, monthly mean of the weekly series).

A scenario is a path of CHANGES for the next 12 months, applied to the latest actual values:
  baseline  - the Fed 2026 supervisory baseline shape (national)
  recession - the Fed 2026 severely adverse shape (national), starting at the forecast origin
  growth    - not from the Fed: 20th/80th percentile of historical 12-month changes, ramped linearly
The same delta paths are applied at past origins in the backtest, so scenarios are scored like forecasts.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = Path(__file__).parent / "data" / "macro_monthly.csv"
SCENARIO_YAML = ROOT / "sources" / "macro_scenarios.yaml"
COLS = ["ur", "lhpi", "mort"]          # lhpi = log of the house price index
H = 12
SCENARIOS = ("baseline", "recession", "growth")
SERIES_IDS = {"ur": "CASAND5URN", "hpi": "SDXRSA", "mort": "MORTGAGE30US_M"}
ASSUMPTIONS = {
    "baseline": ["Macro follows the Federal Reserve 2026 supervisory baseline shape (unemployment drifts down, "
                 "mortgage rates ease, house prices roughly flat), applied to the latest San Diego values."],
    "recession": ["Macro follows the Federal Reserve 2026 severely adverse shape: unemployment rises about 5 points "
                  "to near 10%, house prices fall roughly 25% within a year, mortgage rates ease. A stress test, "
                  "not a prediction."],
    "growth": ["A documented upside, not a Fed path: unemployment, house prices and mortgage rates move as in the "
               "favorable end (20th or 80th percentile) of San Diego's own 12-month changes."],
}


def load_snapshot(path: Path = SNAPSHOT) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["month"]).set_index("month")
    df.index = df.index.to_period("M").to_timestamp()
    return df[["ur", "hpi", "mort"]]


def to_model_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """raw: columns ur, hpi, mort on a monthly index. Returns ur, lhpi, mort, forward-filled to the last row."""
    df = raw.copy()
    df["lhpi"] = np.log(df["hpi"])
    return df[COLS].sort_index().ffill()


def _interp_months(q: list[float]) -> np.ndarray:
    """Quarterly values (index 0 = Q1 2026) to months 0..12 after the origin (linear)."""
    return np.interp(np.arange(0, H + 1) / 3.0, np.arange(len(q)), q)


def load_fed(path: Path = SCENARIO_YAML) -> dict:
    return yaml.safe_load(Path(path).read_text())


def fed_deltas(fed: dict, scenario: str) -> np.ndarray:
    """(H, 3) change path in [ur pp, log hpi, mort pp] from the Fed baseline's own Q1 2026 jump-off."""
    b, s = fed["baseline"], fed[scenario]
    ur = _interp_months(s["unemployment"])[1:] - b["unemployment"][0]
    lh = np.log(_interp_months(s["house_price_index"])[1:]) - np.log(b["house_price_index"][0])
    mo = _interp_months(s["mortgage_rate"])[1:] - b["mortgage_rate"][0]
    return np.column_stack([ur, lh, mo])


def growth_deltas(macro: pd.DataFrame, q: float = 0.8) -> np.ndarray:
    """Favorable-end 12-month changes from history, ramped linearly (low unemployment and rates, high prices)."""
    d12 = (macro - macro.shift(12)).dropna()
    end = np.array([d12["ur"].quantile(1 - q), d12["lhpi"].quantile(q), d12["mort"].quantile(1 - q)])
    return np.outer(np.arange(1, H + 1) / H, end)


def scenario_deltas(macro: pd.DataFrame, fed: dict | None = None) -> dict[str, np.ndarray]:
    fed = fed or load_fed()
    return {"baseline": fed_deltas(fed, "baseline"), "recession": fed_deltas(fed, "recession"),
            "growth": growth_deltas(macro, fed.get("growth", {}).get("favorable_quantile", 0.8))}


def flat_deltas() -> np.ndarray:
    return np.zeros((H, 3))


def scenario_levels(macro: pd.DataFrame, deltas: np.ndarray) -> pd.DataFrame:
    """Levels (ur, hpi, mort) for the 12 months after the last row of macro."""
    last = macro.iloc[-1]
    idx = pd.date_range(macro.index[-1] + pd.offsets.MonthBegin(1), periods=H, freq="MS")
    return pd.DataFrame({"ur": last["ur"] + deltas[:, 0], "hpi": np.exp(last["lhpi"] + deltas[:, 1]),
                         "mort": last["mort"] + deltas[:, 2]}, index=idx)
