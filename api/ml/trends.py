"""ZIP and listing trend metrics (night-forecast). Market signals, never legal findings."""
import numpy as np
import pandas as pd

from api import db

ZIP_SERIES_SQL = ("SELECT geo_id AS zip, metric, period, value::float8 AS value FROM area_metrics "
                  "WHERE geo_type = 'zip' AND metric IN ('zori', 'zhvi') AND source_key = 'zillow_research' "
                  "AND period >= now() - INTERVAL '4 years' ORDER BY geo_id, metric, period")
NOTE = {"zori": "Rents", "zhvi": "Home values"}


def _monthly(rows: list[tuple]) -> pd.Series:
    if not rows:               # a ZIP with no index data (e.g. a Facebook listing outside the 12 ZIPs)
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(d): float(v) for d, v in rows}).sort_index()
    s.index = s.index.to_period("M").to_timestamp()
    return s[~s.index.duplicated(keep="last")].asfreq("MS").interpolate(limit_area="inside").dropna()


def series_metrics(s: pd.Series) -> dict | None:
    """YoY, annualized 3-month momentum, acceleration (change in YoY over 3 months, pp) and volatility."""
    if len(s) < 16:
        return None
    last = float(s.iloc[-1])
    yoy = (last / s.iloc[-13] - 1) * 100
    yoy_prev = (s.iloc[-4] / s.iloc[-16] - 1) * 100
    mom = ((last / s.iloc[-4]) ** 4 - 1) * 100
    vol = float(s.pct_change().dropna().iloc[-24:].std() * 100)
    return {"as_of": s.index[-1].date(), "latest_usd": round(last, 2), "yoy_pct": round(float(yoy), 2),
            "momentum_3m_pct": round(float(mom), 2), "acceleration_pp": round(float(yoy - yoy_prev), 2),
            "volatility_pct": round(vol, 2)}


def _percentile(value: float, others: list[float]) -> float | None:
    if not others:
        return None
    return round(float(np.mean([o <= value for o in others]) * 100), 1)


def zip_signals(metric: str, m: dict, vol_median: float | None) -> list[dict]:
    name = NOTE[metric]
    out = []
    p = m.get("county_percentile")
    if p is not None and p >= 90:
        out.append({"kind": "fast_rise", "label": f"{name} rising faster than {p:.0f}% of covered ZIPs",
                    "detail": f"{m['yoy_pct']:+.1f}% over 12 months"})
    elif p is not None and p <= 10:
        out.append({"kind": "fast_fall", "label": f"{name} falling or rising slower than {100 - p:.0f}% of covered ZIPs",
                    "detail": f"{m['yoy_pct']:+.1f}% over 12 months"})
    a = m.get("acceleration_pp")
    if a is not None and a >= 1.5:
        out.append({"kind": "accelerating", "label": f"{name} growth is speeding up",
                    "detail": f"YoY rose {a:.1f} points in 3 months"})
    elif a is not None and a <= -1.5:
        out.append({"kind": "decelerating", "label": f"{name} growth is slowing",
                    "detail": f"YoY fell {abs(a):.1f} points in 3 months"})
    v = m.get("volatility_pct")
    if v is not None and vol_median and v >= 1.5 * vol_median and v > 0.5:
        out.append({"kind": "volatile", "label": f"{name} are bouncing more than usual",
                    "detail": f"monthly swings {v:.1f}% vs {vol_median:.1f}% typical"})
    return out


def zip_trends(zip_: str) -> dict:
    rows = db.fetch(ZIP_SERIES_SQL)
    by: dict[tuple[str, str], list] = {}
    for r in rows:
        by.setdefault((r["zip"], r["metric"]), []).append((r["period"], r["value"]))
    result = {"zip": zip_, "name": db.ZIP_NAMES.get(zip_, zip_), "signals": []}
    for metric, key in (("zori", "rent"), ("zhvi", "value")):
        stats = {z: series_metrics(_monthly(v)) for (z, mt), v in by.items() if mt == metric}
        stats = {z: m for z, m in stats.items() if m}
        mine = stats.get(zip_)
        if not mine:
            continue
        mine["county_percentile"] = _percentile(mine["yoy_pct"], [m["yoy_pct"] for z, m in stats.items() if z != zip_])
        vols = [m["volatility_pct"] for m in stats.values()]
        result[key] = {"metric": metric, **mine}
        result["signals"] += zip_signals(metric, mine, float(np.median(vols)))
    return result


# ---------- listings ----------
def price_changes(obs: list[dict]) -> list[dict]:
    """Price changes from one listing's observations (oldest first). A 'removed' event followed by a higher
    price is a relist jump."""
    changes, prev, prev_t, removed = [], None, None, False
    for o in obs:
        if o["event"] == "removed":
            removed = True
            continue
        price, t = float(o["price_usd"]), pd.Timestamp(o["observed_at"])
        if prev is not None and price != prev:
            pct = (price / prev - 1) * 100
            kind = "relist_jump" if (removed and price > prev) else ("cut" if price < prev else "raise")
            changes.append({"date": t.date(), "from_usd": prev, "to_usd": price, "change_pct": round(pct, 1),
                            "kind": kind, "days_since_previous": int((t - prev_t).days)})
        if prev is None or price != prev:
            prev_t = t
        prev, removed = price, False
    return changes


def listing_signals(changes: list[dict], vs_zip: float | None, zip_change: float | None, total: float) -> list[dict]:
    out = []
    cuts = [c for c in changes if c["kind"] == "cut"]
    if len(cuts) >= 2:
        out.append({"kind": "repeated_cuts", "label": f"Price cut {len(cuts)} times",
                    "detail": f"{sum(c['change_pct'] for c in cuts):.1f}% in total"})
    jumps = [c for c in changes if c["kind"] == "relist_jump"]
    if jumps:
        j = jumps[-1]
        out.append({"kind": "relist_jump", "label": "Came back on the market at a higher price",
                    "detail": f"{j['change_pct']:+.1f}% after being removed"})
    if vs_zip is not None and abs(vs_zip) >= 3:
        if vs_zip < 0:
            lbl = ("Price fell while the ZIP's typical rent rose" if (zip_change or 0) > 0 and total < 0
                   else "Price moved below the ZIP's typical rent trend")
            out.append({"kind": "below_zip_trend", "label": lbl, "detail": f"{vs_zip:+.1f} points vs the ZIP"})
        else:
            out.append({"kind": "above_zip_trend", "label": "Price rose faster than the ZIP's typical rent",
                        "detail": f"{vs_zip:+.1f} points vs the ZIP"})
    return out


def _zip_change(zip_: str | None, start, end) -> float | None:
    if not zip_:
        return None
    s = _monthly([(r["month"], r["value"]) for r in db.zori_monthly(zip_)])
    if s.empty:
        return None
    a = s[s.index <= pd.Timestamp(start).to_period("M").to_timestamp()]
    b = s[s.index <= pd.Timestamp(end).to_period("M").to_timestamp()]
    if a.empty or b.empty:
        return None
    return round(float((b.iloc[-1] / a.iloc[-1] - 1) * 100), 1)


def listing_trends(listing_id: int) -> dict | None:
    row = db.listing_one(listing_id)
    if row is None:
        return None
    obs = [o for o in db.listing_observations([listing_id]) if o["listing_id"] == listing_id]
    priced = [o for o in obs if o["event"] != "removed"]
    if not priced:
        return None
    first, cur = float(priced[0]["price_usd"]), float(priced[-1]["price_usd"])
    total = round((cur / first - 1) * 100, 1)
    changes = price_changes(obs)
    zc = _zip_change(row.get("zip"), priced[0]["observed_at"], priced[-1]["observed_at"])
    vs = round(total - zc, 1) if zc is not None else None
    return {"listing_id": listing_id, "zip": row.get("zip"), "first_price_usd": first, "current_price_usd": cur,
            "total_change_pct": total, "zip_change_pct": zc, "vs_zip_pp": vs, "changes": changes,
            "signals": listing_signals(changes, vs, zc, total), "n_observations": len(obs)}
