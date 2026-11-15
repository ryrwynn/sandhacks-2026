"""Tracker endpoints: GET /listings, /listings/{id}, /market. Read-only; every number is from stored data."""
import re
import statistics
import threading
import time
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query

from api import db
from api.routers._common import estimate, label_for, percentile_of, safe
from api.routers.listings import make_estimate
from contracts.api_models import (ListingDetail, ListingsResponse, ListingSummary, MarketForecastPoint,
                                  MarketPoint, MarketRange, MarketResponse, Observation, SparkPoint,
                                  ZipForecastSummary)

router = APIRouter(tags=["tracker"])
MAX_IDS = 50
MIN_MONTH_LISTINGS = 5
_RANGE_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}
_LABEL_TTL = 600
_label_cache: dict = {}
_label_lock = threading.Lock()
_KEEP_UPPER = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}


# ---------- helpers ----------
def pretty_address(a: str | None) -> str | None:
    if not a or not a.strip():
        return None
    words = []
    for w in a.strip().split():
        u = w.upper().strip(",")
        if u in _KEEP_UPPER:
            words.append(u)
        elif re.fullmatch(r"\d+(ST|ND|RD|TH)", u):
            words.append(u.lower())
        elif re.fullmatch(r"[A-Z]?\d+[A-Z]?", u):
            words.append(u)
        else:
            words.append("-".join(p.capitalize() for p in w.split("-")))
    return " ".join(words)


def _f(v):
    return None if v is None else float(v)


def sparkline(obs: list[dict]) -> list[SparkPoint]:
    """One point per month, the last observation in that month. Months without observations get no point."""
    by_month: dict[date, float] = {}
    for o in sorted((o for o in obs if o["event"] != "removed"), key=lambda o: o["observed_at"]):
        by_month[o["observed_at"].date().replace(day=1)] = float(o["price_usd"])
    return [SparkPoint(month=m, price_usd=v) for m, v in sorted(by_month.items())]


def group_label(zip_: str | None, beds: int | None, price: float) -> str | None:
    """Fair-rent label from the ZIP-and-bedroom estimate, computed once per group and cached."""
    if not zip_ or beds is None:
        return None
    key = (zip_.strip(), beds)
    with _label_lock:
        hit = _label_cache.get(key)
    if hit is None or time.monotonic() - hit[0] > _LABEL_TTL:
        est, _, _ = estimate({"zip": key[0], "beds": beds})
        hit = (time.monotonic(), est)
        with _label_lock:
            _label_cache[key] = hit
    est = hit[1]
    return None if est is None else label_for(price, est)


def summary(r: dict, obs: list[dict]) -> ListingSummary:
    zip_ = r["zip"].strip() if r["zip"] else None
    rent = r["listing_type"] == "rent"
    return ListingSummary(
        id=r["listing_id"], address=pretty_address(r.get("address_norm")), unit_label=r.get("unit_label"),
        neighborhood=db.ZIP_NAMES.get(zip_), zip=zip_, beds=r["beds"], baths=_f(r["baths"]), sqft=r["sqft"],
        property_type=r.get("property_type"), listing_type=r["listing_type"],
        current_price_usd=float(r["cur"]), first_price_usd=float(r["first_price"]),
        first_observed=r["first_observed"], n_observations=r["n"], sparkline=sparkline(obs),
        fair_rent_label=group_label(zip_, r["beds"], float(r["cur"])) if rent else None,
        last_seen=r["last_seen"], active=bool(r["active"]),
        source_url=r.get("source_url") if r.get("source_kind") == "listing_site" else None)


def _obs_by_listing(ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for o in safe(db.listing_observations, ids, default=[]):
        out.setdefault(o["listing_id"], []).append(o)
    return out


# ---------- GET /listings ----------
@router.get("/listings", response_model=ListingsResponse)
def list_listings(zip: str | None = Query(None, pattern=r"^\d{5}$"), beds: int | None = Query(None, ge=0, le=10),
                  type: str | None = Query(None, pattern="^(apartment|condo|house)$"),
                  max_price: float | None = Query(None, gt=0),
                  sort: str = Query("recent", pattern="^(recent|price_asc|price_desc|biggest_drop)$"),
                  limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0),
                  ids: str | None = None,
                  min_observations: int | None = Query(None, ge=1, le=100)) -> ListingsResponse:
    id_list = None
    if ids is not None:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(422, "ids must be comma-separated integers")
        if not id_list or len(id_list) > MAX_IDS:
            raise HTTPException(422, f"ids takes 1 to {MAX_IDS} listing ids")
        limit = max(limit, len(id_list))
    rows = safe(db.listing_page, zip, beds, type, max_price, sort, limit, offset, id_list, min_observations,
                default=[])
    obs = _obs_by_listing([r["listing_id"] for r in rows]) if rows else {}
    items = [summary(r, obs.get(r["listing_id"], [])) for r in rows]
    if id_list is not None:  # keep the order the caller asked for
        pos = {i: n for n, i in enumerate(id_list)}
        items.sort(key=lambda it: pos.get(it.id, 0))
    total = rows[0]["total"] if rows else 0
    return ListingsResponse(items=items, total=total, limit=limit, offset=offset)


# ---------- GET /listings/{id} ----------
def _forecast_summary(zip_: str | None) -> ZipForecastSummary | None:
    if not zip_ or zip_ not in db.ZIP_NAMES:
        return None
    rows = safe(db.series, zip_, "zori", default=[])
    actual = [r for r in rows if r["kind"] == "actual"]
    fc = [r for r in rows if r["kind"] == "forecast"]
    latest = db.num(actual[-1]["value"]) if actual else None
    if not fc:
        return ZipForecastSummary(zip=zip_, name=db.ZIP_NAMES[zip_], latest_usd=_f(latest))
    last = fc[-1]
    mape = _f(fc[0]["backtest_mape"])
    m = safe(db.forecast_run_metrics, fc[0]["run_id"], default={}) or {}
    naive = (m.get("by_series") or {}).get(f"{zip_}:zori", {}).get("naive_mape", m.get("naive_mape"))
    end = _f(last["value"])
    return ZipForecastSummary(
        zip=zip_, name=db.ZIP_NAMES[zip_], latest_usd=_f(latest), forecast_12m_usd=end,
        change_pct=round((end / float(latest) - 1) * 100, 2) if end and latest else None,
        lo80_usd=_f(last["lo80"]), hi80_usd=_f(last["hi80"]), backtest_mape=mape, naive_mape=_f(naive),
        beats_naive=(mape < float(naive)) if mape is not None and naive is not None else None)


@router.get("/listings/{listing_id}", response_model=ListingDetail)
def listing_detail(listing_id: int) -> ListingDetail:
    r = safe(db.listing_one, listing_id)
    if r is None:
        raise HTTPException(404, f"No listing {listing_id}")
    obs = _obs_by_listing([listing_id]).get(listing_id, [])
    head = summary(r, obs)
    est = pct = None
    comps: list[float] = []
    if r["listing_type"] == "rent" and head.zip:
        coords = safe(db.listing_coords, listing_id, default={}) or {}
        row = {"zip": head.zip, "beds": r["beds"], "baths": head.baths, "sqft": r["sqft"],
               "year_built": r.get("year_built"), "property_type": r.get("property_type") or "unknown",
               "lat": coords.get("lat"), "lng": coords.get("lng")}
        e, comps, metrics = estimate(row)
        if e is not None:
            est = make_estimate(e, metrics)
            pct = percentile_of(head.current_price_usd, comps)
            head.fair_rent_label = label_for(head.current_price_usd, e)
    return ListingDetail(
        **head.model_dump(),
        observations=[Observation(date=o["observed_at"].date(), event=o["event"], price_usd=float(o["price_usd"]))
                      for o in obs],
        year_built=r.get("year_built"), estimate=est, percentile=pct, n_comparables=len(comps),
        forecast=_forecast_summary(head.zip))


# ---------- GET /market ----------
def _month_name(d: date) -> str:
    return d.strftime("%b %Y")


@router.get("/market", response_model=MarketResponse)
def market(zip: str | None = Query(None, pattern=r"^\d{5}$"), beds: int | None = Query(None, ge=0, le=10),
           type: str | None = Query(None, pattern="^(apartment|condo|house)$"),
           range: MarketRange = "1y") -> MarketResponse:
    if zip is not None and zip not in db.ZIP_NAMES:
        raise HTTPException(404, f"{zip} is not one of the ZIPs RentOrKnot covers")
    notes: list[str] = []
    zori = {r["month"]: float(r["value"]) for r in safe(db.zori_monthly, zip, default=[])}
    if beds is None:
        series = {m: (v, "zori", None) for m, v in zori.items()}
        if type:
            notes.append("ZORI is not split by property type, so the property type filter does not change the "
                         "rent line; pick a bedroom count to see listing medians.")
    else:
        meds = {r["month"]: (float(r["value"]), int(r["n"]))
                for r in safe(db.listing_monthly_medians, zip, beds, type, default=[])
                if int(r["n"]) >= MIN_MONTH_LISTINGS}
        series = {}
        for m in sorted(set(zori) | set(meds)):
            series[m] = (meds[m][0], "listings", meds[m][1]) if m in meds else (zori[m], "zori", None)
    months = sorted(series)
    if range != "all" and months:
        last = months[-1]
        idx = last.year * 12 + last.month - 1 - _RANGE_MONTHS[range]
        floor = date(idx // 12, idx % 12 + 1, 1)
        months = [m for m in months if m >= floor]
    points = [MarketPoint(month=m, value=round(series[m][0], 2), basis=series[m][1], n_listings=series[m][2])
              for m in months]
    if beds is not None:
        fell_back = [p.month for p in points if p.basis == "zori"]
        if fell_back:
            notes.append(f"{len(fell_back)} month(s) use ZORI because fewer than {MIN_MONTH_LISTINGS} "
                         f"{beds}-bedroom listings had a price then: {_month_name(fell_back[0])} to "
                         f"{_month_name(fell_back[-1])}. ZORI covers all bedroom counts.")
        if fell_back and len(fell_back) < len(points):
            notes.append("Listing medians (current asking rents) and ZORI (an index of typical rent) measure "
                         "different things, so a step where the source changes is not a market move.")
    cur = points[-1].value if points else None
    change = since = None
    if len(points) > 1 and points[0].value and len({p.basis for p in points}) == 1:
        change, since = round((cur / points[0].value - 1) * 100, 2), points[0].month
    elif len({p.basis for p in points}) > 1:
        # ZORI (an index of typical rent) and listing medians (asking rents) are different measures: a step
        # between them is not a market move, so no percentage change is reported for a mixed series.
        notes.append("No percentage change is shown because this range mixes ZORI and listing medians.")

    fc_rows = safe(db.forecast_latest, zip, default=[])
    forecast = [MarketForecastPoint(month=r["month"], value=round(float(r["value"]), 2),
                                    lo80=round(float(r["lo80"]), 2), hi80=round(float(r["hi80"]), 2))
                for r in fc_rows if r["lo80"] is not None and r["hi80"] is not None]
    mape = naive = beats = None
    if fc_rows:
        mape = _f(fc_rows[0]["backtest_mape"])
        mt = safe(db.forecast_run_metrics, fc_rows[0]["run_id"], default={}) or {}
        by = mt.get("by_series") or {}
        if zip:
            naive = by.get(f"{zip}:zori", {}).get("naive_mape", mt.get("naive_mape"))
        else:
            vals = [v["naive_mape"] for k, v in by.items() if k.endswith(":zori") and "naive_mape" in v]
            naive = statistics.fmean(vals) if vals else mt.get("naive_mape")
        if mape is not None:
            mape = round(mape, 2)
        if mape is not None and naive is not None:
            beats = mape < float(naive)
        naive = None if naive is None else round(float(naive), 2)
    active = safe(db.active_rent_count, zip, beds, type, default=0) or 0
    updated = safe(db.last_scrape_at)
    return MarketResponse(zip=zip, beds=beds, property_type=type, range=range, points=points, forecast=forecast,
                          current_value=cur, change_pct=change, change_since=since, active_listings=active,
                          updated_at=updated if isinstance(updated, datetime) else None,
                          backtest_mape=mape, naive_mape=naive, beats_naive=beats, notes=notes)
