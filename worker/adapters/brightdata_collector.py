"""Bright Data AI Scraper Studio collector adapter (apartments_com; disabled until a collector exists).

Read-only: it starts a collector run over public search pages and downloads the result.
"""
import logging
import os
import time
from typing import Iterator

import httpx

from worker.adapters.base import RawRecord, SourceAdapter
from worker.clean import content_hash, redact_text
from worker.mapping import load_zips

log = logging.getLogger("worker.brightdata")
API = "https://api.brightdata.com/dca"


class BrightDataCollectorAdapter(SourceAdapter):
    fetch_method = "brightdata_collector"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {os.environ['BRIGHTDATA_API_TOKEN']}"}

    def fetch(self, inputs: list[dict] | None = None) -> Iterator[RawRecord]:
        f = self.template["fetch"]
        if not f.get("collector_id"):
            raise RuntimeError("apartments_com needs BRIGHTDATA_APARTMENTS_COLLECTOR (a collector built in AI Scraper Studio)")
        inputs = inputs or [{"url": f["input_url"].format(zip=z)} for z in load_zips(f["zip_file"])]
        r = httpx.post(f"{API}/trigger", params={"collector": f["collector_id"], "queue_next": 1},
                       headers=self._headers(), json=inputs, timeout=120)
        r.raise_for_status()
        rid = r.json()["response_id"]
        for _ in range(120):
            d = httpx.get(f"{API}/dataset", params={"id": rid}, headers=self._headers(), timeout=120)
            if d.status_code == 200 and isinstance(d.json(), list):
                for row in d.json():
                    p = self.drop_personal(row)
                    for fld in self.template.get("redact_fields") or []:
                        if isinstance(p.get(fld), str):
                            p[fld] = redact_text(p[fld])
                    yield RawRecord(self.source_key, p, content_hash(p, self.template.get("hash_ignore")), rid)
                return
            time.sleep(30)
        raise TimeoutError("collector run did not finish")
