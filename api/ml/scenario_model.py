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
ALPHA = 30.0
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CSV = {"zori": DATA_DIR / "zillow_zori_sd.csv", "zhvi": DATA_DIR / "zillow_zhvi_sd.csv"}
WINDOW = 32              # complete origins used to rescale the cone


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


def split(origins_: np.ndarray, warm: int = 5, cal_frac: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Warm-up origins (their errors only seed the cone) and the held-out test origins that are scored."""
    return np.arange(0, warm), np.arange(warm, len(origins_))


def _q(err, origins_, i, h):
    """10th/90th percentile of pooled errors at horizon h from origins whose outcome was known at origin i."""
    known = np.where(origins_ + (h + 1) <= origins_[i])[0]
    if len(known) < 2:
        return None
    e = err[known, h, :].ravel()
    return min(np.quantile(e, 0.1), -1e-4), max(np.quantile(e, 0.9), 1e-4)


def _scale(err, origins_, i, window=WINDOW) -> float | None:
    """Rolling conformal multiplier at origin i: the 0.8 quantile of the multipliers that would just have covered
    each recent fully-observed (origin, horizon, zip) outcome, given that origin's own quantile band."""
    done = [j for j in range(len(origins_)) if origins_[j] + H <= origins_[i]][-window:]
    need = []
    for j in done:
        for h in range(H):
            q = _q(err, origins_, j, h)
            if q is None:
                continue
            e = err[j, h]
            need.append(np.where(e >= 0, e / q[1], e / q[0]))
    if len(need) < 4:
        return None
    return float(np.quantile(np.concatenate(need), 0.8))


def cone(pred: np.ndarray, err: np.ndarray, origins_: np.ndarray, idx: np.ndarray):
    """Rolling-conformal 80% cone (log scale) at origins idx. pred, err (O, H, Z). Returns lo, hi, k per origin."""
    lo = np.full((len(idx), H, pred.shape[2]), np.nan)
    hi, ks = lo.copy(), np.full(len(idx), np.nan)
    for n, i in enumerate(idx):
        k = _scale(err, origins_, i)
        if k is None:
            continue
        ks[n] = k
        for h in range(H):
            q = _q(err, origins_, i, h)
            if q is not None:
                lo[n, h] = pred[i, h] + k * q[0]
                hi[n, h] = pred[i, h] + k * q[1]
    return lo, hi, ks


def coverage(actual, lo, hi) -> float:
    ok = ~np.isnan(lo)
    return float(((actual >= lo) & (actual <= hi))[ok].mean()) if ok.any() else float("nan")


def mape(pred, actual) -> np.ndarray:
    """Per-zip mean absolute percentage error over origins and horizons; arrays (O, H, Z) in logs."""
    return (np.abs(np.exp(pred) - np.exp(actual)) / np.exp(actual)).mean(axis=(0, 1)) * 100


def _cov_by_zip(actual, lo, hi):
    return np.array([coverage(actual[:, :, z], lo[:, :, z], hi[:, :, z]) for z in range(actual.shape[2])])


def evaluate(bt: dict) -> dict:
    """Per-zip results on the held-out test origins (after a warm-up). The cone at each origin uses only errors
    already observed at that origin, so coverage on the test origins is out-of-sample."""
    O = bt["origins"]
    cal, test = split(O)
    actual = bt["actual"]
    methods = {"naive": bt["naive"], "own": bt["own"], "baseline": bt["x_flat"],
               "recession": bt["x_recession"], "growth": bt["x_growth"], "oracle": bt["x_oracle"]}
    if "ets" in bt:
        methods["ets"] = bt["ets"]
    base_err = actual - bt["x_flat"]
    res = {}
    for name, pred in methods.items():
        r = {"mape": mape(pred[test], actual[test])}
        if name == "ets":
            lo, hi = bt["ets_lo"][test], bt["ets_hi"][test]
        elif name != "naive":
            # baseline and the scenarios share the baseline's calibrated residual band, re-centred on their own mean;
            # own and oracle use their own residuals
            src_err = base_err if name in ("recession", "growth") else actual - pred
            src_pred = bt["x_flat"] if name in ("recession", "growth") else pred
            lo, hi, ks = cone(src_pred, src_err, O, test)
            lo, hi = lo - src_pred[test] + pred[test], hi - src_pred[test] + pred[test]
            r["k_last"] = float(ks[~np.isnan(ks)][-1]) if (~np.isnan(ks)).any() else None
        else:
            res[name] = r
            continue
        r["coverage"] = _cov_by_zip(actual[test], lo, hi)
        r["coverage_all"] = coverage(actual[test], lo, hi)
        res[name] = r
    return {"origins": O, "test": test, "cal": cal, "zips": bt["zips"], "methods": res,
            }


# ---------- production forecast ----------
def forecast_all(panel: pd.DataFrame, macro_frame: pd.DataFrame, bt: dict, fed: dict | None = None) -> dict:
    """Forecast every scenario for every ZIP from the last month. Returns {scenario: {"model", "months", "mean",
    "lo", "hi"}} with arrays (H, Z) in dollars. The cone is the baseline backtest's per-horizon error quantiles
    (all origins), scaled by the rolling conformal multiplier at the final origin."""
    Y = np.log(panel.to_numpy())
    M = align_macro(panel, macro_frame)
    t = len(Y) - 1
    deltas = mc.scenario_deltas(macro_frame, fed or mc.load_fed())
    models = fit(Y, M, t, True)
    err = bt["actual"] - bt["x_flat"]
    O = np.append(bt["origins"], bt["origins"][-1] + STEP * 5)   # a virtual final origin: all backtest origins are observed
    k = _scale(np.concatenate([err, err[-1:]]), O, len(O) - 1) or 1.0
    q = [(np.quantile(err[:, h].ravel(), 0.1), np.quantile(err[:, h].ravel(), 0.9)) for h in range(H)]
    qlo, qhi = np.array([a for a, _ in q])[:, None], np.array([b for _, b in q])[:, None]
    months = pd.date_range(panel.index[-1] + pd.offsets.MonthBegin(1), periods=H, freq="MS")
    out = {}
    for s in mc.SCENARIOS:
        mean = Y[t] + predict(models, Y, t, deltas[s])
        out[s] = {"model": "pooled_x", "months": months, "mean": np.exp(mean),
                  "lo": np.exp(mean + k * qlo), "hi": np.exp(mean + k * qhi), "k": k}
    return out
