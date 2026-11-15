"""Pooled direct ridge model with macro regressors, rolling-origin backtest and cone calibration (night-forecast).

For each horizon h = 1..12, one ridge regression pooled over ZIPs:
    log(y[t+h]) - log(y[t]) ~ own momentum at t (1, 3 and 12 month log change) + macro change between t and t+h
                              (unemployment pp, log house price index, mortgage rate pp)
Macro changes are the realized path in training, and a scenario path (api/ml/macro.py) when forecasting.
The 80% cone is the empirical 10th/90th percentile of past rolling-origin errors per horizon, scaled by a
multiplier chosen on a calibration window and then scored on later, held-out origins.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from api.ml import macro as mc
from api.ml.forecast import _ets_forecast

H = mc.H
MIN_ORIGIN = 60          # first backtest origin index (needs a few years of training)
STEP = 3                 # backtest every third month
ALPHA = 3.0
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CSV = {"zori": DATA_DIR / "zillow_zori_sd.csv", "zhvi": DATA_DIR / "zillow_zhvi_sd.csv"}
K_GRID = np.round(np.arange(0.5, 3.01, 0.05), 2)


# ---------- data ----------
def load_panel_csv(metric: str, path: Path | None = None) -> pd.DataFrame:
    """Committed Zillow extract -> DataFrame (months x ZIPs) of dollar values on a month-start index."""
    df = pd.read_csv(path or CSV[metric], dtype={"RegionName": str})
    dates = [c for c in df.columns if c[:2] == "20" and c[4] == "-"]
    wide = df.set_index("RegionName")[dates].T
    wide.index = pd.to_datetime(wide.index).to_period("M").to_timestamp()
    return wide.astype(float).interpolate(limit_area="inside").dropna(how="any")


def panel_from_series(series: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.DataFrame(series)
    df.index = pd.DatetimeIndex(df.index).to_period("M").to_timestamp()
    return df.interpolate(limit_area="inside").dropna(how="any")


def align_macro(panel: pd.DataFrame, macro_frame: pd.DataFrame) -> np.ndarray:
    """Macro (ur, lhpi, mort) on the panel's index; forward-fills the late-published tail, back-fills nothing."""
    m = macro_frame.reindex(macro_frame.index.union(panel.index)).sort_index().ffill()
    return m.reindex(panel.index)[mc.COLS].to_numpy()


# ---------- model ----------
def _own(Y: np.ndarray) -> np.ndarray:
    """(T, Z, 3) momentum features; rows before month 12 are NaN."""
    f = np.full(Y.shape + (3,), np.nan)
    f[1:, :, 0] = Y[1:] - Y[:-1]
    f[3:, :, 1] = (Y[3:] - Y[:-3]) / 3
    f[12:, :, 2] = (Y[12:] - Y[:-12]) / 12
    return f


def fit(Y: np.ndarray, M: np.ndarray, t: int, use_macro: bool = True) -> list:
    """Models for h = 1..H trained on origins s with s + h <= t."""
    own = _own(Y)
    Z = Y.shape[1]
    models = []
    for h in range(1, H + 1):
        s = np.arange(12, t - h + 1)
        X = own[s].reshape(-1, 3)
        if use_macro:
            dm = M[s + h] - M[s]
            X = np.hstack([X, np.repeat(dm, Z, axis=0)])
        y = (Y[s + h] - Y[s]).reshape(-1)
        sc = StandardScaler().fit(X)
        models.append((sc, Ridge(alpha=ALPHA).fit(sc.transform(X), y)))
    return models


def predict(models: list, Y: np.ndarray, t: int, deltas: np.ndarray | None) -> np.ndarray:
    """(H, Z) predicted log changes from origin t. deltas (H, 3) is the macro path; None = no macro features."""
    own = _own(Y)[t]
    out = np.zeros((H, Y.shape[1]))
    for h, (sc, rg) in enumerate(models):
        X = own
        if deltas is not None:
            X = np.hstack([own, np.repeat(deltas[h][None], Y.shape[1], axis=0)])
        out[h] = rg.predict(sc.transform(X))
    return out


# ---------- backtest ----------
def origins(n: int) -> list[int]:
    return list(range(MIN_ORIGIN, n - H, STEP))


def _ets_log(panel: pd.DataFrame, t: int):
    """ETS mean and 80% PI as log arrays (H, Z) from origin t."""
    means, los, his = [], [], []
    for z in panel.columns:
        f = _ets_forecast(panel[z].iloc[: t + 1], H)
        means.append(np.log(f["mean"].to_numpy()))
        los.append(np.log(f["pi_lower"].to_numpy()))
        his.append(np.log(f["pi_upper"].to_numpy()))
    return np.array(means).T, np.array(los).T, np.array(his).T


def backtest(panel: pd.DataFrame, macro_frame: pd.DataFrame, fed: dict | None = None, with_ets: bool = True) -> dict:
    """Rolling-origin backtest. Returns arrays over (origin, horizon, zip) of log forecasts for each method:
    naive, ets, own (pooled, no macro), x_flat (baseline backtest: macro held flat), x_recession, x_growth,
    x_oracle (realized macro) and the log actuals."""
    Y = np.log(panel.to_numpy())
    M = align_macro(panel, macro_frame)
    fed = fed or mc.load_fed()
    deltas = mc.scenario_deltas(macro_frame, fed)
    O = origins(len(Y))
    keys = ["naive", "own", "x_flat", "x_recession", "x_growth", "x_oracle", "actual"] + (["ets", "ets_lo", "ets_hi"] if with_ets else [])
    res = {k: [] for k in keys}
    for t in O:
        mx, mo = fit(Y, M, t, True), fit(Y, M, t, False)
        res["naive"].append(np.repeat(Y[t][None], H, axis=0))
        res["own"].append(Y[t] + predict(mo, Y, t, None))
        res["x_flat"].append(Y[t] + predict(mx, Y, t, mc.flat_deltas()))
        res["x_recession"].append(Y[t] + predict(mx, Y, t, deltas["recession"]))
        res["x_growth"].append(Y[t] + predict(mx, Y, t, deltas["growth"]))
        res["x_oracle"].append(Y[t] + predict(mx, Y, t, M[t + 1: t + H + 1] - M[t]))
        res["actual"].append(Y[t + 1: t + H + 1])
        if with_ets:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m, lo, hi = _ets_log(panel, t)
            res["ets"].append(m); res["ets_lo"].append(lo); res["ets_hi"].append(hi)
    out = {k: np.array(v) for k, v in res.items()}
    out["origins"] = np.array(O)
    out["zips"] = list(panel.columns)
    return out


def split(origins_: np.ndarray, warm: int = 6, cal_frac: float = 0.55) -> tuple[np.ndarray, np.ndarray]:
    """Index sets: calibration and held-out test origins (after a warm-up so residual pools are non-empty)."""
    idx = np.arange(warm, len(origins_))
    cut = warm + int(len(idx) * cal_frac)
    return np.arange(warm, cut), np.arange(cut, len(origins_))


def online_quantiles(err: np.ndarray, origins_: np.ndarray, i: int, h: int):
    """10th/90th percentile of pooled errors for horizon h from origins whose outcome was known at origin i."""
    known = np.where(origins_ + (h + 1) <= origins_[i])[0]
    if len(known) < 2:
        return None
    e = err[known, h, :].ravel()
    return np.quantile(e, 0.1), np.quantile(e, 0.9)


def cone(pred: np.ndarray, err: np.ndarray, origins_: np.ndarray, idx: np.ndarray, k: float):
    """Online empirical cone (log scale) for origins idx. pred, err are (O, H, Z). Returns lo, hi (len(idx), H, Z)."""
    lo = np.full((len(idx), H, pred.shape[2]), np.nan)
    hi = lo.copy()
    for j, i in enumerate(idx):
        for h in range(H):
            q = online_quantiles(err, origins_, i, h)
            if q is None:
                continue
            lo[j, h] = pred[i, h] + k * q[0]
            hi[j, h] = pred[i, h] + k * q[1]
    return lo, hi


def coverage(actual, lo, hi) -> float:
    ok = ~np.isnan(lo)
    return float(((actual >= lo) & (actual <= hi))[ok].mean()) if ok.any() else float("nan")


def mape(pred, actual) -> np.ndarray:
    """Per-zip mean absolute percentage error over origins and horizons; arrays (O, H, Z) in logs."""
    return (np.abs(np.exp(pred) - np.exp(actual)) / np.exp(actual)).mean(axis=(0, 1)) * 100


def choose_k(pred, actual, origins_, cal_idx) -> float:
    """Smallest multiplier whose calibration-window coverage reaches 0.80 (closest to 0.80 if none exact)."""
    err = actual - pred
    best, gap = 1.0, 9.0
    for k in K_GRID:
        lo, hi = cone(pred, err, origins_, cal_idx, k)
        g = abs(coverage(actual[cal_idx], lo, hi) - 0.8)
        if g < gap - 1e-9:
            best, gap = float(k), g
    return best


def evaluate(bt: dict) -> dict:
    """Per-zip results on the held-out test origins (cone multipliers fixed on the calibration origins)."""
    O = bt["origins"]
    cal, test = split(O)
    actual = bt["actual"]
    out = {"origins": O, "cal": cal, "test": test, "zips": bt["zips"]}
    methods = {"naive": bt["naive"], "own": bt["own"], "baseline": bt["x_flat"],
               "recession": bt["x_recession"], "growth": bt["x_growth"], "oracle": bt["x_oracle"]}
    if "ets" in bt:
        methods["ets"] = bt["ets"]
    res = {}
    for name, pred in methods.items():
        r = {"mape": mape(pred[test], actual[test])}
        if name in ("baseline", "own", "oracle", "recession", "growth"):
            k = choose_k(bt["x_flat"], actual, O, cal) if name in ("recession", "growth") else choose_k(pred, actual, O, cal)
            err_src = bt["x_flat"] if name in ("recession", "growth") else pred
            # scenario cones reuse the baseline's calibrated residuals around the scenario's own mean
            e = actual - err_src
            lo, hi = cone(err_src, e, O, test, k)
            lo, hi = lo - err_src[test] + pred[test], hi - err_src[test] + pred[test]
            r["k"] = k
            r["coverage"] = np.array([coverage(actual[test][:, :, z], lo[:, :, z], hi[:, :, z]) for z in range(actual.shape[2])])
            r["coverage_all"] = coverage(actual[test], lo, hi)
        if name == "ets":
            lo, hi = bt["ets_lo"][test], bt["ets_hi"][test]
            r["coverage"] = np.array([coverage(actual[test][:, :, z], lo[:, :, z], hi[:, :, z]) for z in range(actual.shape[2])])
            r["coverage_all"] = coverage(actual[test], lo, hi)
        res[name] = r
    out["methods"] = res
    out["cal_mape"] = {n: mape(m[cal], actual[cal]) for n, m in methods.items()}
    return out


# ---------- production forecast ----------
def forecast_all(panel: pd.DataFrame, macro_frame: pd.DataFrame, bt: dict, k: float, fed: dict | None = None,
                 model_for_baseline: str = "pooled_x") -> dict:
    """Forecast every scenario for every ZIP from the last month. Returns {scenario: {"model", "months", "mean",
    "lo", "hi"}} with arrays (H, Z) in dollars. Cone: all past baseline errors, per horizon, scaled by k."""
    Y = np.log(panel.to_numpy())
    M = align_macro(panel, macro_frame)
    t = len(Y) - 1
    deltas = mc.scenario_deltas(macro_frame, fed or mc.load_fed())
    models = fit(Y, M, t, True)
    err = bt["actual"] - bt["x_flat"]
    O = bt["origins"]
    q = [(np.quantile(err[:, h].ravel(), 0.1), np.quantile(err[:, h].ravel(), 0.9)) for h in range(H)]
    months = pd.date_range(panel.index[-1] + pd.offsets.MonthBegin(1), periods=H, freq="MS")
    out = {}
    for s in mc.SCENARIOS:
        mean = Y[t] + predict(models, Y, t, deltas[s])
        lo = mean + k * np.array([a for a, _ in q])[:, None]
        hi = mean + k * np.array([b for _, b in q])[:, None]
        out[s] = {"model": "pooled_x", "months": months, "mean": np.exp(mean), "lo": np.exp(lo), "hi": np.exp(hi)}
    return out
