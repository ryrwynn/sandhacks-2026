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
from contracts.api_models import (ListingDetail, ListingsResponse, ListingSource, ListingSummary, ListingTag,
                                  MarketForecastPoint, MarketPoint, MarketRange, MarketResponse, Observation,
                                  SourceBreakdown, SourceStat, SparkPoint, UnitType, ZipForecastSummary)

router = APIRouter(tags=["tracker"])
MAX_IDS = 50
MIN_MONTH_LISTINGS = 5
MIN_CHANGE_LISTINGS = 30      # both months need this many listings before a listing-median % change is shown
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


SOURCE_LABELS = {"zillow_rent": "Zillow", "zillow_sale": "Zillow", "apartments_com": "Apartments.com",
                 db.FB_SOURCE: "Facebook group"}


def _date(v):
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _dt(v):
    try:
        return datetime.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


# ---------- card tags (real data only) ----------
MAX_TAGS = 4
FB_AMENITY_TAGS = {"parking": "Parking", "laundry": "Laundry", "pets_allowed": "Pets allowed",
                   "utilities_included": "Utilities included"}
# Zillow unit_amenities values -> tag; values not listed here (oven, flooring types, ...) make no tag.
ZILLOW_AMENITY_TAGS = {"washer": "Washer & dryer", "dryer": "Washer & dryer", "dishwasher": "Dishwasher",
                       "hardwood": "Hardwood floors"}
AREA_FEATURES = {"groceries": "Groceries nearby (ZIP)", "transit_stops": "Transit stops nearby (ZIP)",
                 "parks": "Parks nearby (ZIP)"}
_AREA_TTL = 600
_area_cache: dict = {"at": 0.0, "tags": {}}


def area_tags_by_zip(feats: dict[str, dict]) -> dict[str, list[str]]:
    """ZIP -> area tags: a feature tags a ZIP when its count per km² is in the top third of the 12 ZIPs."""
    out: dict[str, list[str]] = {}
    for key, label in AREA_FEATURES.items():
        dens = {z: float(f[key]) / float(f["area_km2"]) for z, f in feats.items()
                if f.get(key) is not None and f.get("area_km2")}
        if len(dens) < 3:
            continue
        ranked = sorted(dens.values(), reverse=True)
        cutoff = ranked[len(dens) // 3 - 1]
        if cutoff <= ranked[-1]:            # all (or the top third) tied with the lowest: nothing stands out
            continue
        for z in (z for z in dens if dens[z] >= cutoff):
            out.setdefault(z, []).append(label)
    return out


def _area_tags(zip_: str | None) -> list[str]:
    if not zip_:
        return []
    if time.monotonic() - _area_cache["at"] > _AREA_TTL or not _area_cache["tags"]:
        feats = safe(db.zip_features, default={}) or {}
        _area_cache.update(at=time.monotonic(), tags=area_tags_by_zip(feats))
    return list(_area_cache["tags"].get(zip_, []))


def listing_tags(amenities, fb: bool, zip_: str | None) -> list[ListingTag]:
    labels: list[str] = []
    for a in amenities or []:
        name = str(a).strip()
        label = FB_AMENITY_TAGS.get(name) if fb else ZILLOW_AMENITY_TAGS.get(name.lower())
        if label and label not in labels:
            labels.append(label)
    tags = [ListingTag(label=x, kind="listing") for x in labels]
    tags += [ListingTag(label=x, kind="area") for x in _area_tags(zip_)]
    return tags[:MAX_TAGS]


def summary(r: dict, obs: list[dict]) -> ListingSummary:
    """Facebook rows: only extracted fields; address, unit, text, names and profile links are never returned."""
    zip_ = r["zip"].strip() if r["zip"] else None
    rent = r["listing_type"] == "rent"
    fb = r.get("source_key") == db.FB_SOURCE
    unit = r.get("unit_type") if fb else None
    labelled = rent and (not fb or unit == "entire_unit")   # a room isn't priced against whole units
    return ListingSummary(
        id=r["listing_id"], address=None if fb else pretty_address(r.get("address_norm")),
        unit_label=None if fb else r.get("unit_label"),
        neighborhood=(r.get("post_neighborhood") or db.ZIP_NAMES.get(zip_)) if fb else db.ZIP_NAMES.get(zip_),
        zip=zip_, beds=r["beds"], baths=_f(r["baths"]), sqft=r["sqft"],
        property_type=r.get("property_type"), listing_type=r["listing_type"],
        current_price_usd=float(r["cur"]), first_price_usd=float(r["first_price"]),
        first_observed=r["first_observed"], n_observations=r["n"], sparkline=sparkline(obs),
        fair_rent_label=group_label(zip_, r["beds"], float(r["cur"])) if labelled else None,
        last_seen=r["last_seen"], active=bool(r["active"]),
        source_url=r.get("source_url") if r.get("source_kind") == "listing_site" else None,
        source_kind="social" if fb else "listing_site",
        source_label=SOURCE_LABELS.get(r.get("source_key") or "", None),
        unit_type=unit, location_precision=r.get("location_precision") or "address",
        post_url=r.get("post_url") if fb else None, group_name=r.get("group_name") if fb else None,
        posted_at=_dt(r.get("posted_at")) if fb else None, available_date=_date(r.get("available_date")),
        amenities=list(r.get("amenities") or []) if fb else [], unusual_price=bool(r.get("unusual_price")),
        trust_weight=0.5 if fb else 1.0,
        roommate_wanted=bool(r.get("roommate_wanted")) and fb and unit == "room",
        tags=listing_tags(r.get("amenities"), fb, zip_))


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
                  min_observations: int | None = Query(None, ge=1, le=100),
                  source: ListingSource = "all", unit_type: UnitType | None = None) -> ListingsResponse:
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
                source, unit_type, default=[])
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
    fb = head.source_kind == "social"
    if r["listing_type"] == "rent" and head.zip and (not fb or head.unit_type == "entire_unit"):
        if fb:   # Facebook: ZIP and beds only; no building facts exist (and none are ever made from posts)
            row = {"zip": head.zip, "beds": r["beds"], "baths": None, "sqft": None, "year_built": None,
                   "property_type": "unknown", "lat": None, "lng": None}
        else:
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
        year_built=None if fb else r.get("year_built"), estimate=est, percentile=pct, n_comparables=len(comps),
        forecast=_forecast_summary(head.zip))


# ---------- GET /market ----------
def _month_name(d: date) -> str:
    return d.strftime("%b %Y")


def _stat(pairs: list[tuple[float, float]]) -> SourceStat:
    m = db.weighted_median(pairs)
    return SourceStat(count=len(pairs), median_usd=None if m is None else round(m, 2))


def source_breakdown(rows: list[dict], listing_sites_only: bool = False) -> SourceBreakdown:
    """Active listings by source. Facebook whole units count at weight 0.5; rooms/sublets and unusual prices are
    reported apart and never enter the whole-unit median."""
    ls, fb, fb_med, rooms, unusual = [], [], [], [], 0
    for r in rows:
        pair = (float(r["cur"]), float(r["w"] or 1))
        if r["kind"] == "listing_site":
            ls.append(pair)
        elif r["source_key"] == db.FB_SOURCE and r["unit_type"] == "entire_unit":
            fb.append(pair)
            if r["unusual"]:
                unusual += 1
            else:
                fb_med.append(pair)
        elif r["source_key"] == db.FB_SOURCE and r["unit_type"] in ("room", "sublet"):
            rooms.append(pair)
    fb_stat = SourceStat(count=len(fb), median_usd=_stat(fb_med).median_usd)
    return SourceBreakdown(listing_sites=_stat(ls), facebook=fb_stat, facebook_rooms=_stat(rooms),
                           facebook_unusual=unusual, listing_sites_only=listing_sites_only)


@router.get("/market", response_model=MarketResponse)
def market(zip: str | None = Query(None, pattern=r"^\d{5}$"), beds: int | None = Query(None, ge=0, le=10),
           type: str | None = Query(None, pattern="^(apartment|condo|house)$"),
           range: MarketRange = "1y", listing_sites_only: bool = False) -> MarketResponse:
    if zip is not None and zip not in db.ZIP_NAMES:
        raise HTTPException(404, f"{zip} is not one of the ZIPs RentOrKnot covers")
    notes: list[str] = []
    zori = {r["month"]: float(r["value"]) for r in safe(db.zori_monthly, zip, default=[])}
    meds: dict = {}
    if beds is not None:
        meds = {r["month"]: (float(r["value"]), int(r["n"]))
                for r in safe(db.listing_monthly_medians, zip, beds, type, listing_sites_only, default=[])
                if int(r["n"]) >= MIN_MONTH_LISTINGS}
    elif type:
        notes.append("ZORI is not split by property type, so the property type filter does not change the "
                     "rent line; pick a bedroom count to see listing medians.")
    # Two separate series, never spliced: ZORI (Zillow's typical rent, all bedroom counts) for every month, and,
    # with a bedroom filter, the median asking rent of our listings for months with enough listings. Points are
    # ordered by month, ZORI first within a month, so the last point is the newest value.
    months = sorted(set(zori) | set(meds))
    if range != "all" and months:
        last = months[-1]
        idx = last.year * 12 + last.month - 1 - _RANGE_MONTHS[range]
        floor = date(idx // 12, idx % 12 + 1, 1)
        months = [m for m in months if m >= floor]
    points = []
    for m in months:
        if m in zori:
            points.append(MarketPoint(month=m, value=round(zori[m], 2), basis="zori", n_listings=None))
        if m in meds:
            points.append(MarketPoint(month=m, value=round(meds[m][0], 2), basis="listings", n_listings=meds[m][1]))
    zp = [p for p in points if p.basis == "zori"]
    lp = [p for p in points if p.basis == "listings"]
    if beds is not None:
        if lp:
            notes.append(f"The dotted line is the median asking rent of {beds}-bedroom listings, shown for months with "
                         f"at least {MIN_MONTH_LISTINGS} listings ({len(lp)} in this range). The solid line is ZORI, "
                         "Zillow's typical rent across all bedroom counts; the two measure different things.")
        else:
            notes.append(f"Fewer than {MIN_MONTH_LISTINGS} {beds}-bedroom listings had a price in every month of "
                         "this range, so only ZORI (all bedroom counts) is shown.")
    head = lp if beds is not None and lp else zp      # the headline value: the bedroom median when there is one
    cur = head[-1].value if head else None
    change = since = None
    if head is lp:   # a % change between listing medians only when both months have a solid sample
        solid = [p for p in lp if (p.n_listings or 0) >= MIN_CHANGE_LISTINGS]
        if len(solid) > 1 and solid[-1] is lp[-1]:
            change, since = round((cur / solid[0].value - 1) * 100, 2), solid[0].month
        elif len(lp) > 1:
            notes.append(f"No percentage change is shown: earlier months have fewer than {MIN_CHANGE_LISTINGS} "
                         f"{beds}-bedroom listings, too few to compare with today.")
    elif len(head) > 1 and head[0].value:
        change, since = round((cur / head[0].value - 1) * 100, 2), head[0].month

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
    breakdown = source_breakdown(safe(db.active_by_source, zip, beds, type, default=[]) or [], listing_sites_only)
    active = breakdown.listing_sites.count + (0 if listing_sites_only else breakdown.facebook.count)
    if not listing_sites_only and (breakdown.facebook.count or breakdown.facebook_rooms.count):
        notes.append("Facebook group listings count at half weight; rooms, sublets and unusual prices are left "
                     "out of the whole-unit numbers.")
    updated = safe(db.last_scrape_at)
    return MarketResponse(zip=zip, beds=beds, property_type=type, range=range, points=points, forecast=forecast,
                          current_value=cur, change_pct=change, change_since=since, active_listings=active,
                          updated_at=updated if isinstance(updated, datetime) else None,
                          backtest_mape=mape, naive_mape=naive, beats_naive=beats, notes=notes,
                          sources=breakdown, listing_sites_only=listing_sites_only)
