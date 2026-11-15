from fastapi import APIRouter, HTTPException

from api import db
from api.ml import scoring
from api.routers._common import safe, zip_data, score_rows
from contracts.api_models import (AmenityCounts, Metric, SeriesPoint, SeriesResponse, ZipProfile, ZipsResponse,
                                  ZipSummary)

router = APIRouter(prefix="/zips", tags=["zips"])


def _summary(d: dict) -> ZipSummary:
    return ZipSummary(zip=d["zip"], name=d["name"], median_rent_by_beds=d["median_rent_by_beds"],
                      typical_rent_usd=d["zori"], typical_home_value_usd=d["zhvi"],
                      rent_forecast_change_pct=d["rent_fc"], value_forecast_change_pct=d["value_fc"],
                      listings_30d=d["listings_30d"])


@router.get("", response_model=ZipsResponse)
def list_zips() -> ZipsResponse:
    return ZipsResponse(zips=[_summary(d) for d in zip_data().values()])


def _int(v):
    return None if v is None else int(v)


@router.get("/{zip}", response_model=ZipProfile)
def zip_profile(zip: str) -> ZipProfile:
    data = zip_data()
    if zip not in data:
        raise HTTPException(404, f"{zip} is not one of the {len(data)} ZIPs RentWatch covers")
    d = data[zip]
    f = d["features"]
    income = f.get("median_income_usd")
    burden = round(d["zori"] / (income / 12) * 100, 1) if d["zori"] and income else None
    yld = round(12 * d["zori"] / d["zhvi"] * 100, 2) if d["zori"] and d["zhvi"] else None
    scores = {}
    rows = score_rows(data, None)
    for persona in ("starter", "wealth"):
        try:
            res = scoring.score_zips(rows, persona, 1e12)
            hit = next((i for i in res["ranked"] + res["stretch"] if i["zip"] == zip), None)
            scores[persona] = None if hit is None else round(hit["score"], 1)
        except NotImplementedError:
            scores[persona] = None
    return ZipProfile(
        zip=zip, name=d["name"], typical_rent_usd=d["zori"], typical_home_value_usd=d["zhvi"],
        median_rent_by_beds=d["median_rent_by_beds"], rent_forecast_change_pct=d["rent_fc"],
        value_forecast_change_pct=d["value_fc"], median_income_usd=income, rent_burden_pct=burden,
        gross_yield_pct=yld,
        amenities=AmenityCounts(groceries=_int(f.get("groceries")), transit_stops=_int(f.get("transit_stops")),
                                parks=_int(f.get("parks")), food_drink=_int(f.get("food_drink")),
                                gyms=_int(f.get("gyms")), area_km2=f.get("area_km2")),
        persona_scores=scores, listings_30d=d["listings_30d"])


@router.get("/{zip}/series", response_model=SeriesResponse)
def zip_series(zip: str, metric: Metric = "zori") -> SeriesResponse:
    if zip not in db.ZIP_NAMES:
        raise HTTPException(404, f"{zip} is not one of the ZIPs RentWatch covers")
    rows = safe(db.series, zip, metric, default=[])
    points = [SeriesPoint(month=r["month"], value=float(r["value"]),
                          lo80=db.num(r["lo80"]), hi80=db.num(r["hi80"]), kind=r["kind"]) for r in rows]
    fc = [r for r in rows if r["kind"] == "forecast"]
    run_id = fc[0]["run_id"] if fc else None
    mape = db.num(fc[0]["backtest_mape"]) if fc else None
    naive = None
    if run_id:
        m = safe(db.forecast_run_metrics, run_id, default={})
        naive = m.get("naive_mape")
    beats = (mape < naive) if mape is not None and naive is not None else None
    return SeriesResponse(zip=zip, metric=metric, points=points, run_id=run_id, backtest_mape=mape,
                          naive_mape=naive, beats_naive=beats)
