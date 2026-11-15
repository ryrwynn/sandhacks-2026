"""GET /geo/zips?bbox= (night-data): which county GeoJSON files and ZCTAs a map viewport needs.

Reads frontend/public/geo/index.json (built by worker.ca_geo): per-county bounding boxes and a bbox per ZCTA.
"""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from contracts.api_models import GeoFile, GeoZipsResponse

router = APIRouter(prefix="/geo", tags=["geo"])
INDEX = Path(__file__).resolve().parents[2] / "frontend" / "public" / "geo" / "index.json"


@lru_cache(maxsize=1)
def _index() -> dict:
    try:
        return json.loads(INDEX.read_text())
    except OSError:
        return {"counties": [], "zips": {}}


def _hit(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def parse_bbox(bbox: str) -> list[float]:
    try:
        v = [float(x) for x in bbox.split(",")]
    except ValueError:
        v = []
    if len(v) != 4 or v[0] > v[2] or v[1] > v[3] or not (-180 <= v[0] <= 180 and -90 <= v[1] <= 90):
        raise HTTPException(422, "bbox must be minLng,minLat,maxLng,maxLat")
    return v


@router.get("/zips", response_model=GeoZipsResponse)
def geo_zips(bbox: str) -> GeoZipsResponse:
    box = parse_bbox(bbox)
    idx = _index()
    files = [GeoFile(county=c["county"], url=c["url"], n_zips=c["n_zips"]) for c in idx["counties"] if _hit(box, c["bbox"])]
    zips = sorted(z for z, b in idx["zips"].items() if _hit(box, b[:4]))
    return GeoZipsResponse(bbox=box, files=files, zips=zips)
