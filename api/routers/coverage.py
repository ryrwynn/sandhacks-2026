"""GET /areas, POST /areas/requests, GET /areas/requests/{id} (night-data). Tables: areas, area_requests.

A request for an area the app doesn't cover yet enters area_requests with a cost estimate and a queue
position. worker.ondemand scrapes the queue inside the daily budget. Nothing here calls Bright Data.
"""
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from api import db
from contracts.api_models import AreaRequestCreate, AreaRequestStatus, AreasResponse, AreaSummary, Tier
from worker import bd

router = APIRouter(prefix="/areas", tags=["coverage"])
COVERED = ("core", "county")
ORDINAL = {1: "next", 2: "2nd", 3: "3rd"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


@router.get("", response_model=AreasResponse)
def list_areas(tier: Tier | None = None, county: str | None = None, q: str | None = None,
               limit: int = 200) -> AreasResponse:
    limit = max(1, min(limit, 2000))
    where, args = ["geo_type = 'zip'"], []
    if tier:
        where.append("tier = %s"); args.append(tier)
    if county:
        where.append("lower(county) = lower(%s)"); args.append(county)
    if q:
        where.append("(name ILIKE %s OR geo_id LIKE %s)"); args += [f"%{q}%", f"{q}%"]
    w = " AND ".join(where)
    try:
        rows = db.fetch(f"SELECT * FROM areas WHERE {w} ORDER BY CASE tier WHEN 'core' THEN 0 WHEN 'county' THEN 1 "
                        f"ELSE 2 END, name, geo_id LIMIT %s", (*args, limit))
        total = db.fetch(f"SELECT count(*) AS n FROM areas WHERE {w}", tuple(args))[0]["n"]
        by_tier = {r["tier"]: r["n"] for r in db.fetch("SELECT tier, count(*) AS n FROM areas GROUP BY tier")}
        ids = [r["geo_id"] for r in rows]
        latest: dict[tuple[str, str], float] = {}
        if ids:
            for m in db.fetch(
                    "SELECT DISTINCT ON (geo_id, metric) geo_id, metric, value FROM ("
                    " SELECT geo_id, metric, value, period FROM area_metrics WHERE geo_type='zip' AND geo_id = ANY(%s) "
                    "  AND metric IN ('zori','zhvi') AND source_key = 'zillow_research' "
                    " UNION ALL SELECT geo_id, metric, value, period FROM staging_area_metrics WHERE geo_type='zip' "
                    "  AND geo_id = ANY(%s) AND metric IN ('zori','zhvi')) u ORDER BY geo_id, metric, period DESC",
                    (ids, ids)):
                latest[(m["geo_id"], m["metric"])] = float(m["value"])
    except db.DBUnavailable:
        return AreasResponse(areas=[], total=0, counts_by_tier={})
    areas = [AreaSummary(
        geo_type=r["geo_type"], geo_id=r["geo_id"], name=r["name"], county=r["county"], tier=r["tier"],
        centroid_lat=r["centroid_lat"], centroid_lng=r["centroid_lng"], has_listings=r["tier"] in COVERED,
        typical_rent_usd=latest.get((r["geo_id"], "zori")), typical_home_value_usd=latest.get((r["geo_id"], "zhvi")),
        last_scraped_at=r["last_scraped_at"]) for r in rows]
    return AreasResponse(areas=areas, total=total, counts_by_tier=by_tier)


def resolve(query: str) -> tuple[str, str, str, list[dict]]:
    """A ZIP or a city name -> (geo_type, geo_id, display name, area rows). 404 when nothing matches."""
    q = query.strip()
    if re.fullmatch(r"\d{5}", q):
        rows = db.fetch("SELECT * FROM areas WHERE geo_type='zip' AND geo_id=%s", (q,))
        if not rows:
            raise HTTPException(404, f"{q} is not a California ZIP RentOrKnot knows")
        return "zip", q, rows[0]["name"], rows
    rows = db.fetch("SELECT * FROM areas WHERE geo_type='zip' AND lower(name)=lower(%s) ORDER BY geo_id", (q,))
    if not rows:
        raise HTTPException(404, f"No California city or ZIP matches '{q}'")
    return "city", _slug(rows[0]["name"]), rows[0]["name"], rows


def _money(usd: float) -> str:
    return f"${usd:.2f}"


def _status(r: dict, *, queue_position: int | None, remaining: float | None, covered: bool = False) -> AreaRequestStatus:
    est = float(r["est_cost_usd"]) if r["est_cost_usd"] is not None else None
    if covered or r["status"] == "loaded":
        msg = f"{r['name']} is already covered." if covered else f"{r['name']} is loaded."
    elif r["status"] == "scraping":
        msg = f"Collecting listings for {r['name']} now."
    elif r["status"] == "failed":
        msg = "We couldn't load this area. Try again later."
    elif r["status"] == "over_budget":
        msg = f"This area is bigger than a day's on-demand budget (about {_money(est or 0)})."
    else:
        place = ORDINAL.get(queue_position or 0, f"{queue_position}th")
        msg = f"Queued: {place} in line, about {_money(est or 0)}."
        if remaining is not None and est is not None and est > remaining:
            msg += " Today's budget is used up, so it runs tomorrow."
    return AreaRequestStatus(
        request_id=r["request_id"], geo_type=r["geo_type"], geo_id=r["geo_id"], name=r["name"], query=r["query"],
        status=r["status"], est_records=r["est_records"], est_cost_usd=est, queue_position=queue_position,
        budget_remaining_usd=remaining, requested_at=r["requested_at"], finished_at=r["finished_at"], message=msg,
        already_covered=covered)


def _queue_info(request_id, requested_at) -> tuple[int | None, float]:
    ahead = db.fetch("SELECT count(*) AS n FROM area_requests WHERE status='queued' AND (requested_at, request_id::text) "
                     "< (%s, %s)", (requested_at, str(request_id)))[0]["n"]
    spent = db.fetch("SELECT COALESCE(sum(est_usd),0) AS s FROM scrape_runs WHERE source_key=%s AND status IN "
                     "('running','ready') AND started_at >= now() - interval '24 hours'", (bd.ONDEMAND_SOURCE,))[0]["s"]
    return ahead + 1, round(max(0.0, bd.ondemand_daily_usd() - float(spent)), 2)


@router.post("/requests", response_model=AreaRequestStatus)
def request_area(req: AreaRequestCreate) -> AreaRequestStatus:
    try:
        gtype, gid, name, areas = resolve(req.query)
        todo = [a for a in areas if a["tier"] not in COVERED]
        covered = not todo
        existing = db.fetch("SELECT * FROM area_requests WHERE geo_type=%s AND geo_id=%s AND status IN "
                            "('queued','scraping') ORDER BY requested_at LIMIT 1", (gtype, gid))
        if existing and not covered:
            row = {**existing[0], "name": name}
        else:
            n_zips = min(len(todo), bd.ONDEMAND_MAX_ZIPS)
            records, usd = bd.estimate(n_zips, bd.ONDEMAND_LIMIT)
            usd = round(usd, 2)                       # the column is NUMERIC(8,2)
            if covered:
                state = "loaded"
            elif usd > bd.ondemand_daily_usd():
                state = "over_budget"
            else:
                state = "queued"
            row = {**db.execute(
                "INSERT INTO area_requests (geo_type, geo_id, query, status, est_records, est_cost_usd, finished_at, note) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (gtype, gid, req.query.strip(), state, records, usd,
                 datetime.now(timezone.utc) if state != "queued" else None,
                 "already covered" if covered else None))[0], "name": name}
        pos, remaining = (None, None)
        if row["status"] == "queued":
            pos, remaining = _queue_info(row["request_id"], row["requested_at"])
        return _status(row, queue_position=pos, remaining=remaining, covered=covered)
    except db.DBUnavailable:
        raise HTTPException(503, "Area requests are unavailable right now")


@router.get("/requests/{request_id}", response_model=AreaRequestStatus)
def area_request(request_id: UUID) -> AreaRequestStatus:
    try:
        rows = db.fetch("SELECT r.*, COALESCE((SELECT name FROM areas a WHERE a.geo_type='zip' AND a.geo_id=r.geo_id LIMIT 1), "
                        "(SELECT name FROM areas a WHERE lower(regexp_replace(a.name,'[^a-zA-Z0-9]+','-','g'))=r.geo_id LIMIT 1), "
                        "r.query) AS name FROM area_requests r WHERE request_id=%s", (str(request_id),))
        if not rows:
            raise HTTPException(404, "No such request")
        row = rows[0]
        pos, remaining = (None, None)
        if row["status"] == "queued":
            pos, remaining = _queue_info(row["request_id"], row["requested_at"])
        return _status(row, queue_position=pos, remaining=remaining, covered=(row["note"] == "already covered"))
    except db.DBUnavailable:
        raise HTTPException(503, "Area requests are unavailable right now")
