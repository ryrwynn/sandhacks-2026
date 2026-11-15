"""OpenStreetMap Overpass adapter: one query per ZIP bounding box, counted inside the ZIP polygon, cached.

Read-only and polite: one query per ZIP with a sleep between them, results cached to data/amenities.json
so the app never calls Overpass at demo time.
"""
import json
import logging
import time
from datetime import date
from typing import Iterator

import httpx

from worker.adapters.base import RawRecord, SourceAdapter
from worker.clean import content_hash
from worker.mapping import ROOT, load_zips
from worker.zip_boundaries import bbox, build_geojson, contains

log = logging.getLogger("worker.overpass")


class OverpassAdapter(SourceAdapter):
    fetch_method = "api"

    def _selectors(self) -> list[tuple[str, str, str]]:
        out = []
        for metric, sels in self.template["tags"].items():
            for s in sels:
                k, v = s.split("=")
                out.append((metric, k, v))
        return out

    def _query(self, box: tuple) -> str:
        s, w, n, e = box
        parts = []
        for _, k, v in self._selectors():
            for el in ("node", "way", "relation"):
                parts.append(f'{el}["{k}"="{v}"]({s},{w},{n},{e});')
        return "[out:json][timeout:120];(" + "".join(parts) + ");out center tags;"

    def _count(self, elements: list[dict], geom: dict) -> dict[str, int]:
        sels = self._selectors()
        counts = {m: 0 for m in self.template["tags"]}
        seen = set()
        for el in elements:
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or not contains(geom, lon, lat):
                continue
            tags = el.get("tags") or {}
            for metric, k, v in sels:
                if tags.get(k) == v and (metric, el["type"], el["id"]) not in seen:
                    seen.add((metric, el["type"], el["id"]))
                    counts[metric] += 1
        return counts

    def _load(self) -> dict:
        f = self.template["fetch"]
        cache = ROOT / f["cache"]
        data = json.loads(cache.read_text()) if cache.exists() else {"fetched_on": date.today().isoformat(), "zips": {}}
        gj_path = ROOT / f["boundaries"]
        gj = json.loads(gj_path.read_text()) if gj_path.exists() else build_geojson()
        geoms = {ft["properties"]["zip"]: ft for ft in gj["features"]}
        for z in load_zips(f["zip_file"]):
            if z in data["zips"] or z not in geoms:
                continue
            feat = geoms[z]
            q = self._query(bbox(feat["geometry"]))
            t0 = time.time()
            last = None
            for attempt in range(2):        # one retry on a busy server, then stop and report
                r = httpx.post(f["url"], data={"data": q}, timeout=180,
                               headers={"User-Agent": "rentwatch-data-worker/0.1", "Accept": "application/json"})
                log.info("overpass %s -> %s in %.1fs", z, r.status_code, time.time() - t0)
                if r.status_code == 200:
                    break
                last = r.status_code
                time.sleep(60)
            else:
                raise RuntimeError(f"overpass failed for {z}: HTTP {last}")
            counts = self._count(r.json()["elements"], feat["geometry"])
            counts["area_km2"] = feat["properties"]["area_km2"]
            data["zips"][z] = counts
            cache.write_text(json.dumps(data, indent=1, sort_keys=True))
            time.sleep(f.get("sleep_seconds", 10))
        return data

    def fetch(self, inputs: list[dict] | None = None) -> Iterator[RawRecord]:
        data = self._load()
        period = date.fromisoformat(data["fetched_on"]).replace(day=1).isoformat()
        for z, counts in data["zips"].items():
            for metric, v in counts.items():
                p = {"metric": metric, "geo_id": z, "period": period, "value": float(v)}
                yield RawRecord(self.source_key, p, content_hash(p))
