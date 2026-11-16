"""Bright Data runs with a budget (night-data). Read-only: asks Bright Data to read public pages.

Every run goes through plan_run (estimate, refuse over budget, write scrape_runs) and run_batch (one batched
trigger, polling with backoff, accounting from delivered records). A new input type needs a 20-record
sample run first; bulk runs refuse without one. The HTTP client and the sleep function are injectable so
tests never touch the network.

Prices (docs/reference/brightdata.md): $1.50 per 1,000 delivered records; bad inputs are still billed.
"""
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

from worker.clean import content_hash

log = logging.getLogger("worker.bd")
API = "https://api.brightdata.com/datasets/v3"
USD_PER_1000 = 1.50
SAMPLE_RECORDS = 20
FB_MAX_PER_GROUP = 50
ONDEMAND_LIMIT = 25              # records per ZIP for an on-demand request
ONDEMAND_MAX_ZIPS = 6            # one city request never fans out past this
ONDEMAND_SOURCE = "zillow_rent_ondemand"
BACKOFF = (5, 10, 20, 40, 60)    # seconds; the last value repeats


class BudgetExceeded(RuntimeError):
    pass


class SampleRequired(RuntimeError):
    pass


def budget_usd() -> float:
    return float(os.environ.get("BRIGHTDATA_BUDGET_USD") or 10)


def ondemand_daily_usd() -> float:
    return float(os.environ.get("ONDEMAND_DAILY_USD") or 1.00)


def estimate(n_inputs: int, limit_per_input: int) -> tuple[int, float]:
    """Worst case: every input returns `limit_per_input` records."""
    records = max(0, n_inputs) * max(0, limit_per_input)
    return records, round(records * USD_PER_1000 / 1000, 4)


def cost_of(records: int) -> float:
    return round(records * USD_PER_1000 / 1000, 4)


# ---------------------------------------------------------------- accounting
def spent_usd(conn, source_key: str | None = None, hours: int = 24) -> float:
    sql = ("SELECT COALESCE(sum(est_usd), 0) FROM scrape_runs WHERE status IN ('running','ready') "
           "AND started_at >= now() - make_interval(hours => %s)")
    args: list = [hours]
    if source_key:
        sql += " AND source_key = %s"
        args.append(source_key)
    return float(conn.execute(sql, args).fetchone()[0])


def sample_done(conn, source_key: str) -> bool:
    return conn.execute("SELECT 1 FROM scrape_runs WHERE source_key = %s AND status = 'ready' AND note LIKE 'sample%%' "
                        "LIMIT 1", (source_key,)).fetchone() is not None


def plan_run(conn, source_key: str, inputs: list, limit: int, *, note: str = "", budget: float | None = None,
             est_per_input: int | None = None) -> dict:
    """Estimate, then either record a 'refused' row and raise, or record an 'estimated' row.
    est_per_input: expected records per input from observed ratios (Zillow overshoots limit_per_input, so the
    limit alone underestimates); default is the worst case at the limit."""
    budget = budget_usd() if budget is None else budget
    records, usd = estimate(len(inputs), est_per_input or limit)
    spent = spent_usd(conn)
    ok = spent + usd <= budget + 1e-9
    row = conn.execute(
        "INSERT INTO scrape_runs (source_key, inputs, n_inputs, records, est_usd, status, note) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING run_id",
        (source_key, json.dumps(inputs), len(inputs), records, usd, "estimated" if ok else "refused",
         (note + f" | spent {spent:.2f} of {budget:.2f}").strip(" |"))).fetchone()
    conn.commit()
    if not ok:
        raise BudgetExceeded(f"{source_key}: estimate ${usd:.2f} + spent ${spent:.2f} would pass the ${budget:.2f} budget")
    return {"run_id": row[0], "est_records": records, "est_usd": usd, "spent_usd": spent}


# ---------------------------------------------------------------- HTTP client
class BrightDataClient:
    """Thin wrapper over the dataset API. The token comes from BRIGHTDATA_API_TOKEN and is never logged."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("BRIGHTDATA_API_TOKEN")

    def _req(self, method: str, path: str, **kw):
        import httpx
        if not self.token:
            raise RuntimeError("BRIGHTDATA_API_TOKEN is not set")
        r = httpx.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {self.token}"}, timeout=120, **kw)
        log.info("brightdata %s %s -> %s", method, path.split("?")[0], r.status_code)
        return r

    def trigger(self, dataset_id: str, inputs: list[dict], limit: int, mode: str = "discover") -> str:
        params = {"dataset_id": dataset_id, "include_errors": "true", "notify": "false", "limit_per_input": limit}
        if mode == "discover":
            params.update({"type": "discover_new", "discover_by": "url"})
        r = self._req("POST", "/trigger", params=params, json=inputs)
        if r.status_code >= 400:
            raise RuntimeError(f"trigger failed: HTTP {r.status_code} {r.text[:150]}")
        return r.json()["snapshot_id"]

    def progress_info(self, snapshot_id: str) -> dict:
        r = self._req("GET", f"/progress/{snapshot_id}")
        if r.status_code >= 400:
            raise RuntimeError(f"progress failed: HTTP {r.status_code}")
        return r.json()

    def progress(self, snapshot_id: str) -> str:
        return self.progress_info(snapshot_id).get("status", "")

    def cancel(self, snapshot_id: str) -> None:
        self._req("POST", f"/snapshot/{snapshot_id}/cancel")

    def snapshot(self, snapshot_id: str) -> list[dict]:
        r = self._req("GET", f"/snapshot/{snapshot_id}", params={"format": "json"})
        if r.status_code != 200:
            raise RuntimeError(f"download failed: HTTP {r.status_code}")
        rows = r.json()
        return rows if isinstance(rows, list) else []


def wait_ready(client, snapshot_id: str, *, max_wait: int = 3600, sleep=time.sleep) -> None:
    waited, i = 0, 0
    while True:
        status = client.progress(snapshot_id)
        if status == "ready":
            return
        if status in ("failed", "canceled") or waited > max_wait:
            raise RuntimeError(f"snapshot {snapshot_id} {status or 'timed out'}")
        d = BACKOFF[min(i, len(BACKOFF) - 1)]
        sleep(d)
        waited += d
        i += 1


# ---------------------------------------------------------------- inputs
def area_slugs() -> dict[str, str]:
    """ZIP -> Zillow city slug from data/areas_ca.csv (ZIPs with no Census place have none)."""
    import csv
    from worker.mapping import ROOT
    with open(ROOT / "data" / "areas_ca.csv") as fh:
        return {r["zip"]: r["city_slug"] for r in csv.DictReader(fh) if r.get("city_slug")}


def zillow_inputs(template: dict, zips: list[str], city_slug: dict[str, str] | None = None) -> list[dict]:
    """Search URLs. City slug precedence: explicit, template city_by_zip, areas_ca.csv, then the template's
    `zip_url` (ZIP-only search, for ZIPs with no city), then san-diego. A wrong city 404s (billed as 1 record)."""
    f = template["fetch"]
    known = area_slugs() if "{city}" in f["input_url"] else {}
    slugs = {**known, **(f.get("city_by_zip") or {}), **(city_slug or {})}
    out = []
    for z in zips:
        if slugs.get(z) or not f.get("zip_url"):
            out.append({"url": f["input_url"].format(zip=z, city=slugs.get(z) or "san-diego")})
        else:
            out.append({"url": f["zip_url"].format(zip=z)})
    return out


def zillow_zip_inputs(template: dict, zips: list[str]) -> list[dict]:
    """ZIP-only search URLs (template fetch.zip_url): about 130 records a ZIP at limit 10, against 5 to 60 for
    the city URL, and no aborted building pages. Used by the county refresh."""
    return [{"url": template["fetch"]["zip_url"].format(zip=z)} for z in zips]


def sample_inputs(inputs: list[dict], limit: int) -> tuple[list[dict], int]:
    """Shrink a batch to a 20-record sample: as many inputs as fit at the per-input cap."""
    cap = max(1, min(limit, SAMPLE_RECORDS))
    return inputs[: max(1, SAMPLE_RECORDS // cap)], cap


def stale_zips(conn, zips: list[str], min_age_days: int) -> list[str]:
    """Incremental: skip ZIPs scraped within `min_age_days` (areas.last_scraped_at)."""
    if not zips:
        return []
    rows = conn.execute("SELECT geo_id FROM areas WHERE geo_type = 'zip' AND geo_id = ANY(%s) AND last_scraped_at "
                        "> now() - make_interval(days => %s)", (zips, min_age_days)).fetchall()
    fresh = {r[0] for r in rows}
    return [z for z in zips if z not in fresh]


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().rstrip("/").encode()).hexdigest()


def newer_posts(rows: list[dict], high_water: dict[str, datetime]) -> list[dict]:
    """Facebook: keep posts newer than each group's high-water mark (group_url hash -> datetime)."""
    out = []
    for r in rows:
        hw = high_water.get(url_hash(r.get("group_url") or ""))
        d = r.get("date_posted")
        try:
            when = datetime.fromisoformat(str(d).replace("Z", "+00:00")) if d else None
        except ValueError:
            when = None
        if hw is None or when is None or when > hw:
            out.append(r)
    return out


# ---------------------------------------------------------------- the run
def run_batch(conn, template: dict, inputs: list[dict], *, limit: int | None = None, sample: bool = False,
              client=None, sleep=time.sleep, note: str = "") -> dict:
    """One batched trigger for `inputs`. Returns {run_id, snapshot_id, rows (personal fields dropped), records, usd}."""
    key = template["source_key"]
    f = template["fetch"]
    limit = limit or f.get("limit_per_input") or 10
    if key.startswith("facebook_groups"):
        limit = min(limit, FB_MAX_PER_GROUP)
    if sample:
        inputs, limit = sample_inputs(inputs, limit)
    elif not sample_done(conn, key):
        raise SampleRequired(f"{key}: run a 20-record sample first (--sample)")
    plan = plan_run(conn, key, inputs, limit, note=("sample " if sample else "bulk ") + note)
    client = client or BrightDataClient()
    conn.execute("UPDATE scrape_runs SET status = 'running' WHERE run_id = %s", (plan["run_id"],))
    conn.commit()
    try:
        snap = client.trigger(f["dataset_id"], inputs, limit, f.get("mode", "discover"))
        conn.execute("UPDATE scrape_runs SET snapshot_id = %s WHERE run_id = %s", (snap, plan["run_id"]))
        conn.commit()
        wait_ready(client, snap, sleep=sleep)
        raw_rows = client.snapshot(snap)
    except Exception as e:
        conn.execute("UPDATE scrape_runs SET status = 'failed', finished_at = now(), note = left(coalesce(note,'') || %s, 400) "
                     "WHERE run_id = %s", (f" | {e}"[:150], plan["run_id"]))
        conn.commit()
        raise
    records = len(raw_rows)                                   # errors are billed too
    usd = cost_of(records)
    conn.execute("UPDATE scrape_runs SET status = 'ready', finished_at = now(), records = %s, est_usd = %s "
                 "WHERE run_id = %s", (records, usd, plan["run_id"]))
    conn.commit()
    cleaner = _Cleaner(template)
    rows = [cleaner.clean_payload(r) for r in raw_rows if isinstance(r, dict) and not r.get("error")]
    return {"run_id": plan["run_id"], "snapshot_id": snap, "rows": rows, "records": records, "usd": usd}


class _Cleaner:
    """clean_payload from the adapter base, without constructing a network adapter."""

    def __init__(self, template: dict):
        from worker.adapters.base import SourceAdapter

        class _A(SourceAdapter):
            def fetch(self, inputs=None):
                return iter(())
        self._a = _A(template)

    def clean_payload(self, row: dict) -> dict:
        return self._a.clean_payload(row)


def store_rows(conn, template: dict, snapshot_id: str, rows: list[dict]) -> int:
    """Cleaned payloads -> raw_records (new content hashes only). Returns how many were new."""
    from worker import load
    n = 0
    for p in rows:
        n += load.store_raw(conn, template["source_key"], snapshot_id, content_hash(p, template.get("hash_ignore")), p)
    conn.commit()
    return n


def mark_scraped(conn, zips: list[str]) -> None:
    if zips:
        conn.execute("UPDATE areas SET last_scraped_at = %s WHERE geo_type = 'zip' AND geo_id = ANY(%s)",
                     (datetime.now(timezone.utc), zips))
        conn.commit()
