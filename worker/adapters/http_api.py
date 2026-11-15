"""Census ACS API adapter: one call per year for all ZIP code tabulation areas, filtered to our ZIPs, cached."""
import json
import logging
import os
from datetime import date
from typing import Iterator

import httpx

from worker.adapters.base import RawRecord, SourceAdapter
from worker.clean import content_hash
from worker.mapping import ROOT, load_zips

log = logging.getLogger("worker.census")


class CensusAcsAdapter(SourceAdapter):
    fetch_method = "api"

    def _query(self) -> dict:
        f = self.template["fetch"]
        cache = ROOT / f["cache"]
        if cache.exists():
            return json.loads(cache.read_text())
        key = os.environ.get(f.get("key_env", "CENSUS_API_KEY"), "")
        variables = list(self.template["variables"])
        last = None
        for year in f["years"]:
            params = {"get": ",".join(variables), "for": "zip code tabulation area:*"}
            if key:
                params["key"] = key
            r = httpx.get(f["url"].format(year=year), params=params, timeout=120)
            log.info("census acs %s -> %s", year, r.status_code)
            if r.status_code == 200:
                table = r.json()
                head, rows = table[0], table[1:]
                zips = set(load_zips(f["zip_file"]))
                zi = head.index("zip code tabulation area")
                out = {"year": year, "rows": {row[zi]: {v: row[head.index(v)] for v in variables}
                                              for row in rows if row[zi] in zips}}
                cache.write_text(json.dumps(out, indent=1))
                return out
            last = r.status_code
        raise RuntimeError(f"census acs failed for years {f['years']}: HTTP {last}")

    def fetch(self, inputs: list[dict] | None = None) -> Iterator[RawRecord]:
        data = self._query()
        period = date(int(data["year"]), 1, 1).isoformat()
        for zip_, vals in data["rows"].items():
            for var, metric in self.template["variables"].items():
                try:
                    v = float(vals[var])
                except (TypeError, ValueError):
                    continue
                if v < 0:               # Census uses large negative numbers for "not available"
                    continue
                p = {"metric": metric, "geo_id": zip_, "period": period, "value": v}
                yield RawRecord(self.source_key, p, content_hash(p))
