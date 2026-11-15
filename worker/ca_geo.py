"""California ZCTA geometry split by county (night-data).

Source: Census TIGERweb 2020 ZCTAs (public), simplified server side with maxAllowableOffset, so no
large shapefile is downloaded. County of a ZCTA = the county holding most of its land, from the Census
ZCTA-county relationship file (streamed to a temp dir, never committed).

uv run python -m worker.ca_geo [--tmp DIR]
Writes frontend/public/geo/<county-slug>.geojson, frontend/public/geo/index.json and data/areas_ca.csv.
"""
import argparse
import csv
import io
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

import httpx

from worker.mapping import ROOT

TIGERWEB = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query"
REL_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"
ZILLOW_ZORI = "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv"
OFFSET_DEG = 0.0012            # about 130 m
GEO_DIR = ROOT / "frontend" / "public" / "geo"
AREAS_CSV = ROOT / "data" / "areas_ca.csv"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _download(url: str, path: Path) -> Path:
    if not path.exists():
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r, path.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return path


def zcta_county(tmp: Path) -> dict[str, str]:
    """ZCTA -> California county name (largest land share)."""
    p = _download(REL_URL, tmp / "rel.txt")
    best: dict[str, tuple[int, str]] = {}
    for row in csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig")), delimiter="|"):
        if not row["GEOID_COUNTY_20"].startswith("06") or not row["GEOID_ZCTA5_20"]:
            continue
        land = int(row["AREALAND_PART"] or 0)
        z = row["GEOID_ZCTA5_20"]
        if z not in best or land > best[z][0]:
            best[z] = (land, row["NAMELSAD_COUNTY_20"].removesuffix(" County"))
    return {z: c for z, (_, c) in best.items()}


def zillow_names(tmp: Path) -> dict[str, dict]:
    """ZIP -> {city, county} from the Zillow ZORI file's labels (California rows only)."""
    p = _download(ZILLOW_ZORI, tmp / "zori.csv")
    out = {}
    with p.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["State"] == "CA":
                out[row["RegionName"].zfill(5)] = {"city": row["City"], "county": row["CountyName"].removesuffix(" County")}
    return out


def fetch_zctas() -> list[dict]:
    feats, offset = [], 0
    while True:
        r = httpx.get(TIGERWEB, timeout=120, params={
            "where": "ZCTA5 >= '90001' AND ZCTA5 <= '96162'", "outFields": "ZCTA5,AREALAND,CENTLAT,CENTLON",
            "outSR": 4326, "f": "geojson", "geometryPrecision": 4, "maxAllowableOffset": OFFSET_DEG,
            "orderByFields": "ZCTA5", "resultOffset": offset, "resultRecordCount": 300})
        r.raise_for_status()
        got = r.json().get("features", [])
        feats += got
        if len(got) < 300:
            return feats
        offset += 300


def bbox_of(geom: dict) -> list[float]:
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    return [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]


def build(tmp: Path) -> dict:
    county_of, labels = zcta_county(tmp), zillow_names(tmp)
    core = dict(ln.split(",", 1) for ln in (ROOT / "data/zips.txt").read_text().splitlines()[1:] if "," in ln)
    by_county: dict[str, list] = defaultdict(list)
    rows = []
    for f in fetch_zctas():
        p = f["properties"]
        z = p["ZCTA5"]
        county = county_of.get(z)
        if not county or not f.get("geometry"):
            continue                               # not a California ZCTA (or no polygon)
        city = labels.get(z, {}).get("city") or ""
        tier = "core" if z in core else ("county" if county == "San Diego" else "index")
        f["properties"] = {"zip": z, "name": city or None, "county": county,
                           "area_km2": round((p["AREALAND"] or 0) / 1e6, 2)}
        by_county[county].append(f)
        rows.append({"zip": z, "name": core.get(z) or city or z, "city": city, "city_slug": slug(city),
                     "county": county, "tier": tier, "lat": p["CENTLAT"], "lng": p["CENTLON"]})
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    index: dict = {"counties": [], "zips": {}}
    for county, feats in sorted(by_county.items()):
        name = f"{slug(county)}.geojson"
        (GEO_DIR / name).write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
        bbs = [bbox_of(f["geometry"]) for f in feats]
        index["counties"].append({"county": county, "url": f"/geo/{name}", "n_zips": len(feats),
                                  "bbox": [min(b[0] for b in bbs), min(b[1] for b in bbs),
                                           max(b[2] for b in bbs), max(b[3] for b in bbs)]})
        for f, b in zip(feats, bbs):
            index["zips"][f["properties"]["zip"]] = b + [slug(county)]
    (GEO_DIR / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    (ROOT / "data" / "geo_index.json").write_text(json.dumps(index, separators=(",", ":")))   # the API image excludes frontend/
    with AREAS_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["zip", "name", "city", "city_slug", "county", "tier", "lat", "lng"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["zip"]))
    return {"zctas": len(rows), "counties": len(by_county),
            "tiers": {t: sum(r["tier"] == t for r in rows) for t in ("core", "county", "index")}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmp", help="temp dir for the Census/Zillow downloads")
    a = ap.parse_args(argv)
    if a.tmp:
        Path(a.tmp).mkdir(parents=True, exist_ok=True)
        print(build(Path(a.tmp)))
    else:
        with tempfile.TemporaryDirectory() as d:
            print(build(Path(d)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
