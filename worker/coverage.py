"""Coverage loader (night-data): areas table, index-tier raw records, county ZIP list, row counts.

uv run python -m worker.coverage seed      # register the new sources (disabled) from db/seed_sources.sql
uv run python -m worker.coverage areas     # areas table from data/areas_ca.csv (+ data/zips_county.txt)
uv run python -m worker.coverage export-index  # keyless: California ZORI/ZHVI -> data/index_ca_zillow.jsonl.gz
uv run python -m worker.coverage index     # that file + Census ACS -> raw_records (needs DATABASE_URL)
uv run python -m worker.coverage counts    # row counts per source and tier

Nothing here writes to listings, properties, price_observations, area_metrics or forecasts.
"""
import argparse
import csv
import gzip
import io
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

import httpx

from worker import load
from worker.clean import content_hash
from worker.mapping import ROOT, load_template

AREAS_CSV = ROOT / "data" / "areas_ca.csv"
COUNTY_ZIPS = ROOT / "data" / "zips_county.txt"
DATE_COL = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Zillow labels some neighborhoods by city; these names are friendlier for the map and search.
NAME_OVERRIDES = {"92037": "La Jolla", "92106": "Point Loma", "92118": "Coronado", "92014": "Del Mar",
                  "92130": "Carmel Valley", "92127": "Rancho Bernardo", "92121": "Sorrento Valley"}


def read_areas() -> list[dict]:
    with AREAS_CSV.open() as f:
        return list(csv.DictReader(f))


def seed(conn) -> int:
    sql = (ROOT / "db" / "seed_sources.sql").read_text()
    conn.execute(sql)
    conn.commit()
    return conn.execute("SELECT count(*) FROM sources").fetchone()[0]


def write_county_zips(rows: list[dict]) -> int:
    lines = ["zip,name"] + [f"{r['zip']},{NAME_OVERRIDES.get(r['zip'], r['name'])}" for r in rows if r["tier"] == "county"]
    COUNTY_ZIPS.write_text("\n".join(lines) + "\n")
    return len(lines) - 1


def load_areas(conn) -> dict:
    rows = read_areas()
    n_county = write_county_zips(rows)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO areas (geo_type, geo_id, name, county, tier, centroid_lat, centroid_lng) "
            "VALUES ('zip', %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (geo_type, geo_id) DO UPDATE SET name = EXCLUDED.name, county = EXCLUDED.county, "
            " centroid_lat = EXCLUDED.centroid_lat, centroid_lng = EXCLUDED.centroid_lng",
            [(r["zip"], NAME_OVERRIDES.get(r["zip"], r["name"]), r["county"], r["tier"], float(r["lat"]), float(r["lng"]))
             for r in rows])
    conn.commit()
    return {"areas": len(rows), "county_zips": n_county}


def _stream(url: str, path: Path) -> Path:
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r, path.open("wb") as f:
        for chunk in r.iter_bytes():
            f.write(chunk)
    return path


def zillow_series(path: Path, metric: str, zips: set[str], months: int):
    """Yield one payload per ZIP: the last `months` monthly values, first-of-month periods."""
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            z = row["RegionName"].zfill(5)
            if row["State"] != "CA" or z not in zips:
                continue
            cols = [c for c in row if DATE_COL.match(c) and row[c] not in ("", None)]
            series = {f"{c[:7]}-01": round(float(row[c]), 2) for c in cols[-months:]}
            if series:
                yield {"metric": metric, "geo_id": z, "series": series}


INDEX_FILE = ROOT / "data" / "index_ca_zillow.jsonl.gz"


def export_index(tmp: Path) -> dict:
    """Keyless: stream Zillow's public CSVs, keep California ZIPs and the last `months` values, write one
    gzip JSON line per (ZIP, metric). The big CSVs are deleted right after."""
    t = load_template("zillow_research_ca")
    zips = {r["zip"] for r in read_areas()}
    n = {}
    with gzip.open(INDEX_FILE, "wt") as out:
        for spec in t["fetch"]["files"]:
            p = _stream(spec["url"], tmp / f"{spec['metric']}.csv")
            n[spec["metric"]] = 0
            for payload in zillow_series(p, spec["metric"], zips, t["fetch"]["months"]):
                out.write(json.dumps(payload, separators=(",", ":")) + "\n")
                n[spec["metric"]] += 1
            p.unlink()
    return n


def load_index_file(conn) -> int:
    n = 0
    with gzip.open(INDEX_FILE, "rt") as f:
        for line in f:
            payload = json.loads(line)
            n += load.store_raw(conn, "zillow_research_ca", f"zillow-research-{payload['metric']}",
                                content_hash(payload), payload)
    conn.commit()
    return n


def load_acs(conn) -> dict:
    t = load_template("census_acs_ca")
    f = t["fetch"]
    key = os.environ.get(f["key_env"], "")
    variables = list(t["variables"])
    zips = {r["zip"] for r in read_areas()}
    for year in f["years"]:
        params = {"get": ",".join(variables), "for": "zip code tabulation area:*"}
        if key:
            params["key"] = key
        r = httpx.get(f["url"].format(year=year), params=params, timeout=120)
        if r.status_code != 200:
            continue
        head, rows = r.json()[0], r.json()[1:]
        zi = head.index("zip code tabulation area")
        n = 0
        for row in rows:
            if row[zi] not in zips:
                continue
            for var, metric in t["variables"].items():
                try:
                    v = float(row[head.index(var)])
                except (TypeError, ValueError):
                    continue
                if v < 0:                            # Census uses large negatives for "not available"
                    continue
                p = {"metric": metric, "geo_id": row[zi], "period": date(int(year), 1, 1).isoformat(), "value": v}
                n += load.store_raw(conn, "census_acs_ca", f"acs5-{year}", content_hash(p), p)
        conn.commit()
        return {"year": year, "records": n}
    raise RuntimeError("census acs: no year answered")


def counts(conn) -> dict:
    out = {"raw_records": dict(conn.execute(
        "SELECT source_key, count(*) FROM raw_records WHERE source_key IN "
        "('zillow_research_ca','census_acs_ca','zillow_rent_county','zillow_rent_ondemand','facebook_groups_sd') "
        "GROUP BY 1 ORDER BY 1").fetchall())}
    out["areas_by_tier"] = dict(conn.execute("SELECT tier, count(*) FROM areas GROUP BY 1 ORDER BY 1").fetchall())
    for t in ("staging_listings", "staging_area_metrics", "fb_groups", "area_requests", "scrape_runs"):
        out[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seed", "areas", "index", "counts", "export-index"])
    a = ap.parse_args(argv)
    if a.cmd == "export-index":
        with tempfile.TemporaryDirectory() as d:
            print(export_index(Path(d)))
        return 0
    conn = load.connect()          # reads DATABASE_URL from the environment
    if a.cmd == "seed":
        print({"sources": seed(conn)})
    elif a.cmd == "areas":
        print(load_areas(conn))
    elif a.cmd == "index":
        print({"zillow_file": load_index_file(conn), "acs": load_acs(conn)})
    else:
        print(json.dumps(counts(conn), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
