"""Bright Data dataset adapter: trigger a discovery run by search URL, poll, download, drop personal fields.

Read-only: it asks Bright Data to read public listing pages and downloads the result. Nothing is posted anywhere.
Snapshots are cached under data/.cache/ (git-ignored) so a crash after the paid run never costs a second run.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Iterator

import httpx

from worker.adapters.base import RawRecord, SourceAdapter
from worker.clean import content_hash, redact_text
from worker.mapping import ROOT, get_path, load_zips

log = logging.getLogger("worker.brightdata")
API = "https://api.brightdata.com/datasets/v3"
CACHE = ROOT / "data" / ".cache"


class BrightDataError(RuntimeError):
    pass


class BrightDataDatasetAdapter(SourceAdapter):
    fetch_method = "brightdata_dataset"

    def __init__(self, template: dict, poll_seconds: int = 30, max_wait: int = 3600):
        super().__init__(template)
        self.poll_seconds, self.max_wait = poll_seconds, max_wait
        self.snapshot_id: str | None = None

    # -- HTTP ---------------------------------------------------------------
    def _headers(self) -> dict:
        token = os.environ.get("BRIGHTDATA_API_TOKEN")
        if not token:
            raise BrightDataError("BRIGHTDATA_API_TOKEN is not set")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _call(self, method: str, url: str, **kw) -> httpx.Response:
        t0 = time.time()
        r = httpx.request(method, url, headers=self._headers(), timeout=120, **kw)
        log.info("brightdata %s %s -> %s in %.1fs", method, url.split("?")[0].replace(API, ""), r.status_code, time.time() - t0)
        return r

    def build_inputs(self) -> list[dict]:
        f = self.template["fetch"]
        if f.get("inputs"):
            return f["inputs"]
        return [{"url": f["input_url"].format(zip=z)} for z in load_zips(f["zip_file"])]

    def trigger(self, inputs: list[dict]) -> str:
        f = self.template["fetch"]
        params = {"dataset_id": f["dataset_id"], "type": "discover_new", "discover_by": f.get("discover_by", "url"),
                  "include_errors": "true"}
        if f.get("limit_per_input"):
            params["limit_per_input"] = f["limit_per_input"]
        r = self._call("POST", f"{API}/trigger", params=params, json=inputs)
        if r.status_code >= 400:
            raise BrightDataError(f"trigger failed: HTTP {r.status_code} {r.text[:200]}")
        return r.json()["snapshot_id"]

    def wait(self, snapshot_id: str) -> None:
        waited = 0
        while True:
            r = self._call("GET", f"{API}/progress/{snapshot_id}")
            if r.status_code >= 400:
                raise BrightDataError(f"progress failed: HTTP {r.status_code} {r.text[:200]}")
            status = r.json().get("status")
            if status == "ready":
                return
            if status == "failed" or waited > self.max_wait:
                raise BrightDataError(f"snapshot {snapshot_id} {status or 'timed out'}")
            time.sleep(self.poll_seconds)
            waited += self.poll_seconds

    def download(self, snapshot_id: str) -> list[dict]:
        cache = CACHE / f"{snapshot_id}.json"
        if cache.exists():
            return json.loads(cache.read_text())
        r = self._call("GET", f"{API}/snapshot/{snapshot_id}", params={"format": "json"})
        if r.status_code >= 400:
            raise BrightDataError(f"download failed: HTTP {r.status_code} {r.text[:200]}")
        rows = r.json()
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows))
        return rows

    # -- adapter ------------------------------------------------------------
    def clean_payload(self, row: dict) -> dict:
        p = self.drop_personal(row)
        for f in self.template.get("redact_fields") or []:
            if isinstance(p.get(f), str):
                p[f] = redact_text(p[f])
        return p

    def fetch(self, inputs: list[dict] | None = None, snapshot_id: str | None = None) -> Iterator[RawRecord]:
        if snapshot_id is None:
            snapshot_id = self.trigger(inputs or self.build_inputs())
            log.info("triggered snapshot %s", snapshot_id)
        self.snapshot_id = snapshot_id
        self.wait(snapshot_id)
        for row in self.download(snapshot_id):
            if not isinstance(row, dict) or row.get("error"):
                continue
            payload = self.clean_payload(row)
            h = content_hash(payload, self.template.get("hash_ignore"))
            yield RawRecord(self.source_key, payload, h, snapshot_id)

    def fetch_rows(self, rows: list[dict], snapshot_id: str | None = None) -> Iterator[RawRecord]:
        """Same cleaning for rows that are already in hand (fixtures, tests)."""
        for row in rows:
            payload = self.clean_payload(row)
            yield RawRecord(self.source_key, payload, content_hash(payload, self.template.get("hash_ignore")), snapshot_id)
