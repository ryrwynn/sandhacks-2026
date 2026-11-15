"""Census ZCTA polygons for our ZIPs (TIGERweb, public) -> data/zips.geojson, plus point-in-polygon and area helpers."""
import json
import math
import logging

import httpx

from worker.mapping import ROOT, load_zips

log = logging.getLogger("worker.zips")
URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query"


def build_geojson(path: str = "data/zips.geojson") -> dict:
    zips = load_zips()
    names = {}
    for line in (ROOT / "data/zips.txt").read_text().splitlines()[1:]:
        z, _, n = line.partition(",")
        names[z.strip()] = n.strip()
    feats = []
    for z in zips:
        r = httpx.get(URL, params={"where": f"ZCTA5='{z}'", "outFields": "ZCTA5,AREALAND", "outSR": 4326,
                                   "f": "geojson", "geometryPrecision": 5}, timeout=120)
        r.raise_for_status()
        got = r.json().get("features", [])
        if not got:
            log.warning("no ZCTA polygon for %s; dropping it", z)   # plan: drop a ZIP that doesn't match
            continue
        f = got[0]
        f["properties"] = {"zip": z, "name": names.get(z), "area_km2": round(area_km2(f["geometry"]), 3)}
        feats.append(f)
    gj = {"type": "FeatureCollection", "features": feats}
    (ROOT / path).write_text(json.dumps(gj, separators=(",", ":")))
    return gj


def _rings(geom: dict) -> list[list[list[float]]]:
    """Outer rings of each polygon followed by holes, as (ring, is_hole) flattened: [outer, hole...] per polygon."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return polys


def point_in_ring(x: float, y: float, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(geom: dict, lng: float, lat: float) -> bool:
    for poly in _rings(geom):
        if point_in_ring(lng, lat, poly[0]) and not any(point_in_ring(lng, lat, h) for h in poly[1:]):
            return True
    return False


def _ring_area_km2(ring) -> float:
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx = 111.320 * math.cos(math.radians(lat0))
    ky = 110.574
    s = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i][0] * kx, ring[i][1] * ky
        x2, y2 = ring[(i + 1) % len(ring)][0] * kx, ring[(i + 1) % len(ring)][1] * ky
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def area_km2(geom: dict) -> float:
    return sum(_ring_area_km2(p[0]) - sum(_ring_area_km2(h) for h in p[1:]) for p in _rings(geom))


def bbox(geom: dict) -> tuple[float, float, float, float]:
    pts = [pt for poly in _rings(geom) for ring in poly for pt in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(ys), min(xs), max(ys), max(xs)     # south, west, north, east
