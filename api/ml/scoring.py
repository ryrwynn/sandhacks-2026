"""Persona scores per ZIP, 0 to 100 (docs/PLAN.md "Persona scores"). Owner: lane C.

Inputs are prices, forecasts, listings and amenities only; never who lives in a ZIP.
"""
from typing import Literal, TypedDict

Persona = Literal["starter", "wealth"]

STARTER_WEIGHTS = {"rent": 0.40, "rent_forecast": 0.20, "basics_density": 0.25,
                   "other_amenities_density": 0.05, "listings_30d": 0.10}
WEALTH_WEIGHTS = {"value_forecast": 0.35, "gross_yield": 0.30, "value_vs_budget": 0.20,
                  "volatility": 0.15}

LABELS = {
    "rent": "Low typical rent",
    "rent_forecast": "Slower rent growth forecast",
    "basics_density": "Groceries and transit nearby",
    "other_amenities_density": "Food, gyms and parks nearby",
    "listings_30d": "Many recent listings",
    "value_forecast": "Strong home-value growth forecast",
    "gross_yield": "High rent compared with home price",
    "value_vs_budget": "Home values well within budget",
    "volatility": "Steady prices",
}
# A lower raw value is better for these (the scaled value is flipped).
LOWER_IS_BETTER = {"rent": True, "rent_forecast": True, "value_vs_budget": True, "volatility": True}


class ZipScoreInput(TypedDict, total=False):
    zip: str
    typical_rent: float | None              # for the chosen bedroom count, else ZORI
    rent_forecast_change_pct: float | None
    groceries: float | None
    transit_stops: float | None
    parks: float | None
    food_drink: float | None
    gyms: float | None
    area_km2: float | None
    listings_30d: int | None
    typical_home_value: float | None        # latest ZHVI
    value_forecast_change_pct: float | None
    value_volatility_5y: float | None       # std of monthly % changes over 5 years


def _density(row, keys) -> float | None:
    area = row.get("area_km2")
    vals = [row.get(k) for k in keys]
    if not area or area <= 0 or all(v is None for v in vals):
        return None
    return sum(v or 0 for v in vals) / area


def _features(row, persona: Persona, budget_usd: float) -> dict:
    if persona == "starter":
        return {
            "rent": row.get("typical_rent"),
            "rent_forecast": row.get("rent_forecast_change_pct"),
            "basics_density": _density(row, ["groceries", "transit_stops"]),
            "other_amenities_density": _density(row, ["food_drink", "gyms", "parks"]),
            "listings_30d": row.get("listings_30d"),
        }
    rent, value = row.get("typical_rent"), row.get("typical_home_value")
    return {
        "value_forecast": row.get("value_forecast_change_pct"),
        "gross_yield": 12 * rent / value if rent is not None and value else None,
        "value_vs_budget": value / budget_usd if value is not None and budget_usd else None,
        "volatility": row.get("value_volatility_5y"),
    }


def _scale(values: list, lower_better: bool) -> list[float]:
    known = [v for v in values if v is not None]
    if len(known) < 2 or max(known) == min(known):
        return [0.5] * len(values)
    lo, hi = min(known), max(known)
    out = []
    for v in values:
        if v is None:
            out.append(0.5)
            continue
        x = (v - lo) / (hi - lo)
        out.append(1 - x if lower_better else x)
    return out


def score_zips(rows: list[ZipScoreInput], persona: Persona, budget_usd: float,
               weights: dict[str, float] | None = None) -> dict:
    """Min-max scale each feature across the given ZIPs, flip where lower is better, weight, x100.
    Budget is a hard filter: starter compares typical_rent, wealth compares typical_home_value.
    Returns {"weights": {...}, "ranked": [item, ...], "stretch": [item, ...]} where item is
    {"zip", "score", "price_usd", "top_contributions": [{"feature", "label", "points", "value"}] (3)}.
    ranked and stretch are each sorted by score, highest first."""
    base = STARTER_WEIGHTS if persona == "starter" else WEALTH_WEIGHTS
    w = dict(base)
    if weights:
        custom = {k: max(float(weights.get(k, 0.0)), 0.0) for k in base}
        total = sum(custom.values())
        if total > 0:
            w = {k: v / total for k, v in custom.items()}

    feats = [_features(r, persona, budget_usd) for r in rows]
    scaled = {k: _scale([f[k] for f in feats], LOWER_IS_BETTER.get(k, False)) for k in w}

    ranked, stretch = [], []
    for i, row in enumerate(rows):
        contribs = [{"feature": k, "label": LABELS[k], "points": w[k] * scaled[k][i] * 100,
                     "value": feats[i][k]} for k in w]
        score = sum(c["points"] for c in contribs)
        top = sorted(contribs, key=lambda c: -c["points"])[:3]
        for c in top:
            c["points"] = round(c["points"], 1)
        price = row.get("typical_rent") if persona == "starter" else row.get("typical_home_value")
        item = {"zip": row["zip"], "score": round(score, 1), "price_usd": price,
                "top_contributions": top}
        (stretch if price is not None and price > budget_usd else ranked).append(item)
    ranked.sort(key=lambda x: -x["score"])
    stretch.sort(key=lambda x: -x["score"])
    return {"weights": w, "ranked": ranked, "stretch": stretch}
