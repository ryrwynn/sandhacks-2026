"""Coverage tests (night-data): areas, on-demand requests, budgeted Bright Data runs, geo, replay.
No test touches the network, a database or Bright Data: the DB and the HTTP client are fakes."""
import csv
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import db
from api.main import app
from worker import bd, ondemand, replay
from worker.mapping import load_template

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


class Cur:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    """handler(sql, args) -> list of tuples; every statement is recorded."""

    def __init__(self, handler=lambda sql, args: []):
        self.handler, self.log = handler, []

    def execute(self, sql, args=None):
        self.log.append((" ".join(sql.split()), args))
        return Cur(self.handler(sql, args))

    def commit(self):
        pass

    def rollback(self):
        pass

    def statuses(self):
        return [a[5] for s, a in self.log if s.startswith("INSERT INTO scrape_runs")]


class FakeClient:
    def __init__(self, n_rows=20, statuses=("running", "ready")):
        self.n_rows, self.statuses, self.calls = n_rows, list(statuses), []

    def trigger(self, dataset_id, inputs, limit, mode="discover"):
        self.calls.append(("trigger", len(inputs), limit, mode))
        return "sd_test"

    def progress(self, sid):
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    def snapshot(self, sid):
        return [{"zpid": i, "price": 2000 + i, "homeStatus": "FOR_RENT", "agentName": "Pat Jones"} for i in range(self.n_rows)]


def spent_handler(spent, sample=True):
    def h(sql, args):
        if "sum(est_usd)" in sql:
            return [(spent,)]
        if "note LIKE" in sql:
            return [(1,)] if sample else []
        if "RETURNING run_id" in sql:
            return [(uuid.uuid4(),)]
        return []
    return h


# ---- pricing and budget --------------------------------------------------------------------------
def test_estimate_uses_the_documented_price():
    assert bd.estimate(100, 10) == (1000, 1.5)
    assert bd.cost_of(2000) == 3.0
    assert bd.estimate(0, 10) == (0, 0.0)


def test_budget_defaults_to_10_and_reads_env(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_BUDGET_USD", raising=False)
    assert bd.budget_usd() == 10
    monkeypatch.setenv("BRIGHTDATA_BUDGET_USD", "3")
    assert bd.budget_usd() == 3


def test_over_budget_trigger_is_refused_and_recorded(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_BUDGET_USD", "10")
    conn = FakeConn(spent_handler(9.99))
    with pytest.raises(bd.BudgetExceeded):
        bd.plan_run(conn, "zillow_rent_county", [{"url": "u"}] * 10, 10)
    assert conn.statuses() == ["refused"]
    ok = FakeConn(spent_handler(0))
    assert bd.plan_run(ok, "zillow_rent_county", [{"url": "u"}] * 10, 10)["est_usd"] == 0.15
    assert ok.statuses() == ["estimated"]


def test_bulk_run_refuses_without_a_sample(monkeypatch):
    t = load_template("zillow_rent_county")
    conn = FakeConn(spent_handler(0, sample=False))
    fake = FakeClient()
    with pytest.raises(bd.SampleRequired):
        bd.run_batch(conn, t, [{"url": "u"}] * 5, client=fake, sleep=lambda s: None)
    assert fake.calls == []


def test_sample_is_at_most_20_records_one_trigger(monkeypatch):
    t = load_template("zillow_rent_county")
    conn = FakeConn(spent_handler(0, sample=False))
    fake = FakeClient(n_rows=18)
    out = bd.run_batch(conn, t, [{"url": f"u{i}"} for i in range(60)], sample=True, client=fake, sleep=lambda s: None)
    assert fake.calls == [("trigger", 2, 10, "discover")]       # 2 inputs x 10 = 20 records at most
    assert out["records"] == 18 and out["usd"] == bd.cost_of(18)
    assert all("agentName" not in r for r in out["rows"])        # personal fields dropped before storage
    assert conn.statuses() == ["estimated"]
    assert any("status = 'ready'" in s for s, _ in conn.log)


def test_failed_snapshot_is_recorded_and_raised():
    t = load_template("zillow_rent_county")
    conn = FakeConn(spent_handler(0))
    with pytest.raises(RuntimeError):
        bd.run_batch(conn, t, [{"url": "u"}], client=FakeClient(statuses=("failed",)), sleep=lambda s: None)
    assert any("status = 'failed'" in s for s, _ in conn.log)


def test_polling_backs_off_and_stops():
    sleeps = []
    fake = FakeClient(statuses=["running"] * 7 + ["ready"])
    bd.wait_ready(fake, "s", sleep=sleeps.append)
    assert sleeps == [5, 10, 20, 40, 60, 60, 60]


def test_facebook_cap_never_exceeds_50():
    t = load_template("facebook_groups_sd")
    assert t["fetch"]["limit_per_input"] <= 50 and t["fetch"]["mode"] == "collect"
    conn = FakeConn(spent_handler(0))
    fake = FakeClient()
    bd.run_batch(conn, t, [{"url": "https://www.facebook.com/groups/x"}], limit=500, client=fake, sleep=lambda s: None)
    assert fake.calls[0][2:] == (50, "collect")


def test_zillow_inputs_use_zillow_city_slugs():
    t = load_template("zillow_rent_county")
    got = bd.zillow_inputs(t, ["92118", "92037"], {"92118": "coronado"})
    assert got[0]["url"] == "https://www.zillow.com/coronado-ca-92118/rentals/"
    assert got[1]["url"] == "https://www.zillow.com/san-diego-ca-92037/rentals/"


def test_facebook_high_water_mark_keeps_only_newer_posts():
    url = "https://www.facebook.com/groups/example"
    hw = {bd.url_hash(url + "/"): datetime(2026, 11, 10, tzinfo=timezone.utc)}
    rows = [{"group_url": url, "date_posted": "2026-11-09T00:00:00Z"}, {"group_url": url, "date_posted": "2026-11-11T00:00:00Z"},
            {"group_url": "https://www.facebook.com/groups/other", "date_posted": "2026-01-01T00:00:00Z"}]
    assert [r["date_posted"][:10] for r in bd.newer_posts(rows, hw)] == ["2026-11-11", "2026-01-01"]


# ---- on-demand job -------------------------------------------------------------------------------
def test_pick_takes_oldest_first_while_the_estimate_fits():
    reqs = [{"id": 1, "est_usd": 0.6}, {"id": 2, "est_usd": 0.6}, {"id": 3, "est_usd": 0.3}]
    taken, deferred = ondemand.pick(reqs, 1.0)
    assert [r["id"] for r in taken] == [1, 3] and [r["id"] for r in deferred] == [2]


def test_ondemand_job_batches_one_trigger_and_stores_raw_only(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_BUDGET_USD", "10")
    monkeypatch.setenv("ONDEMAND_DAILY_USD", "1")
    rid = uuid.uuid4()

    ready = {"yes": False}

    def h(sql, args):
        if "status = 'ready'" in sql and sql.lstrip().startswith("UPDATE"):
            ready["yes"] = True                       # the sample run finished: later runs may go bulk
        if "note LIKE" in sql:
            return [(1,)] if ready["yes"] else []
        if sql.lstrip().startswith("SELECT request_id"):
            return [(rid, "zip", "94110", "94110", 0.04), (uuid.uuid4(), "zip", "94103", "94103", 0.04)]
        if "FROM areas WHERE geo_type='zip' AND geo_id=%s" in sql:
            return [(args[0],)]
        if "SELECT zip, city_slug" in sql:
            return [("94110", "san-francisco"), ("94103", "san-francisco")]
        return spent_handler(0, sample=False)(sql, args)

    conn = FakeConn(h)
    fake = FakeClient(n_rows=20)
    out = ondemand.process_queue(conn, client=fake, sleep=lambda s: None)
    assert out["taken"] == 2 and [c[1] for c in fake.calls] == [1, 2]     # sample, then ONE bulk trigger
    written = {re.match(r"(INSERT INTO|UPDATE|DELETE FROM) (\w+)", s).group(2) for s, _ in conn.log
               if re.match(r"(INSERT INTO|UPDATE|DELETE FROM) (\w+)", s)}
    assert written <= {"scrape_runs", "raw_records", "areas", "area_requests"}


def test_ondemand_dry_run_spends_nothing():
    def h(sql, args):
        if sql.lstrip().startswith("SELECT request_id"):
            return [(uuid.uuid4(), "zip", "94110", "94110", 0.04)]
        if "FROM areas" in sql:
            return [("94110",)]
        return spent_handler(0)(sql, args)
    conn = FakeConn(h)
    assert ondemand.process_queue(conn, client=None, dry_run=True)["taken"] == 1
    assert conn.statuses() == []


# ---- routers -------------------------------------------------------------------------------------
AREAS = {"92037": {"geo_type": "zip", "geo_id": "92037", "name": "La Jolla", "county": "San Diego", "tier": "county",
                   "centroid_lat": 32.85, "centroid_lng": -117.25, "last_scraped_at": None},
         "94110": {"geo_type": "zip", "geo_id": "94110", "name": "San Francisco", "county": "San Francisco", "tier": "index",
                   "centroid_lat": 37.75, "centroid_lng": -122.4, "last_scraped_at": None}}


@pytest.fixture
def fake_db(monkeypatch):
    state = {"requests": []}

    def fetch(sql, params=None):
        if "FROM areas WHERE geo_type='zip' AND geo_id=%s" in sql:
            return [AREAS[params[0]]] if params[0] in AREAS else []
        if "lower(name)=lower" in sql:
            return [a for a in AREAS.values() if a["name"].lower() == params[0].lower()]
        if "SELECT * FROM area_requests WHERE geo_type" in sql:
            return [r for r in state["requests"] if r["geo_id"] == params[1] and r["status"] in ("queued", "scraping")]
        if "count(*) AS n FROM area_requests" in sql:
            return [{"n": 2}]
        if "sum(est_usd)" in sql:
            return [{"s": 0.25}]
        if "SELECT * FROM areas" in sql:
            return list(AREAS.values())
        if "tier, count(*)" in sql:
            return [{"tier": "county", "n": 1}, {"tier": "index", "n": 1}]
        if "count(*) AS n FROM areas" in sql:
            return [{"n": 2}]
        if "FROM area_requests r" in sql:
            return [{**r, "name": "San Francisco"} for r in state["requests"] if str(r["request_id"]) == params[0]]
        return []

    def execute(sql, params=None):
        row = {"request_id": uuid.uuid4(), "geo_type": params[0], "geo_id": params[1], "query": params[2],
               "status": params[3], "est_records": params[4], "est_cost_usd": params[5],
               "requested_at": NOW, "finished_at": params[6], "note": params[7], "started_at": None}
        state["requests"].append(row)
        return [row]

    monkeypatch.setattr(db, "fetch", fetch)
    monkeypatch.setattr(db, "execute", execute)
    monkeypatch.setenv("ONDEMAND_DAILY_USD", "1")
    return state


def test_areas_list(fake_db):
    r = client.get("/areas").json()
    assert r["total"] == 2 and r["counts_by_tier"] == {"county": 1, "index": 1}
    assert {a["tier"] for a in r["areas"]} == {"county", "index"}


def test_areas_without_database_is_empty(monkeypatch):
    def boom(*a, **k):
        raise db.DBUnavailable("down")
    monkeypatch.setattr(db, "fetch", boom)
    assert client.get("/areas").json()["areas"] == []


def test_request_for_covered_zip(fake_db):
    r = client.post("/areas/requests", json={"query": "92037"}).json()
    assert r["already_covered"] and r["status"] == "loaded" and r["queue_position"] is None


def test_request_for_index_zip_gets_estimate_and_queue_position(fake_db):
    r = client.post("/areas/requests", json={"query": "94110"}).json()
    assert r["status"] == "queued" and r["queue_position"] == 3
    assert r["est_records"] == bd.ONDEMAND_LIMIT and r["est_cost_usd"] == round(bd.ONDEMAND_LIMIT * 0.0015, 2)
    assert r["budget_remaining_usd"] == 0.75 and "3rd in line" in r["message"]
    again = client.post("/areas/requests", json={"query": "94110"}).json()      # no duplicate queue entry
    assert again["request_id"] == r["request_id"]
    got = client.get(f"/areas/requests/{r['request_id']}").json()
    assert got["request_id"] == r["request_id"]


def test_request_for_unknown_place_is_404(fake_db):
    assert client.post("/areas/requests", json={"query": "00000"}).status_code == 404
    assert client.post("/areas/requests", json={"query": "Atlantis"}).status_code == 404


# ---- geo -----------------------------------------------------------------------------------------
def test_geo_zips_for_a_san_diego_viewport():
    r = client.get("/geo/zips", params={"bbox": "-117.3,32.7,-117.1,32.9"}).json()
    assert any(f["county"] == "San Diego" and f["url"] == "/geo/san-diego.geojson" for f in r["files"])
    assert "92104" in r["zips"] and "94110" not in r["zips"]


def test_geo_zips_rejects_a_bad_bbox():
    assert client.get("/geo/zips", params={"bbox": "1,2,3"}).status_code == 422
    assert client.get("/geo/zips", params={"bbox": "-117,33,-118,32"}).status_code == 422


def test_geo_files_are_small_and_complete():
    geo = ROOT / "frontend" / "public" / "geo"
    idx = json.loads((geo / "index.json").read_text())
    assert sum(f.stat().st_size for f in geo.iterdir()) < 6_000_000
    assert sum(c["n_zips"] for c in idx["counties"]) == len(idx["zips"]) >= 1700
    for c in idx["counties"]:
        gj = json.loads((ROOT / "frontend" / "public" / c["url"].lstrip("/")).read_text())
        assert len(gj["features"]) == c["n_zips"]


# ---- areas data ----------------------------------------------------------------------------------
def test_area_tiers_in_the_committed_seed():
    rows = list(csv.DictReader((ROOT / "data" / "areas_ca.csv").open()))
    tiers = {t: [r for r in rows if r["tier"] == t] for t in ("core", "county", "index")}
    core = {ln.split(",")[0] for ln in (ROOT / "data" / "zips.txt").read_text().splitlines()[1:]}
    assert {r["zip"] for r in tiers["core"]} == core
    assert all(r["county"] == "San Diego" for r in tiers["county"]) and len(tiers["county"]) >= 90
    assert all(r["county"] != "San Diego" for r in tiers["index"]) and len(tiers["index"]) > 1500
    assert (ROOT / "data" / "zips_county.txt").read_text().count("\n") == len(tiers["county"]) + 1


# ---- safety: sources disabled, replay guarded ----------------------------------------------------------
def test_new_sources_are_registered_disabled_and_enabled_flags_untouched():
    seed = (ROOT / "db" / "seed_sources.sql").read_text()
    for key in ("zillow_research_ca", "census_acs_ca", "zillow_rent_county", "zillow_rent_ondemand", "facebook_groups_sd"):
        assert re.search(rf"'{key}'.*false\)", seed), key
    assert "DO UPDATE" not in seed and "SET enabled" not in seed.lower()


def test_replay_shared_needs_confirmation_and_dev_needs_url(monkeypatch, capsys):
    monkeypatch.delenv("DEV_DATABASE_URL", raising=False)
    assert replay.main(["--source", "zillow_research_ca", "--target", "shared"]) == 2
    assert replay.main(["--source", "zillow_research_ca", "--target", "dev"]) == 2


def test_replay_area_rows_expand_series_and_single_values():
    s = {"metric": "zori", "geo_id": "94110", "series": {"2026-09-01": 3700.0, "2026-10-01": 3720.0}}
    assert replay.area_rows(s) == [("2026-09-01", "94110", 3700.0), ("2026-10-01", "94110", 3720.0)]
    assert replay.area_rows({"metric": "median_income", "geo_id": "92037", "period": "2024-01-01", "value": 1.0}) \
        == [("2024-01-01", "92037", 1.0)]


def test_replay_area_goes_to_staging_under_the_canonical_key():
    t = load_template("zillow_research_ca")
    payload = {"metric": "zori", "geo_id": "94110", "series": {"2026-10-01": 3720.0}}
    conn = FakeConn(lambda sql, args: [(payload,)] if sql.startswith("SELECT payload") else [])

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def executemany(self, sql, batch):
            conn.log.append((" ".join(sql.split()), batch))
    conn.cursor = Cursor
    assert replay.replay_area(conn, t, "staging") == 1
    sql, batch = [x for x in conn.log if x[0].startswith("INSERT INTO")][0]
    assert "staging_area_metrics" in sql and batch[0][-1] == "zillow_research"


def test_facebook_sd_sample_has_no_personal_fields():
    t = load_template("facebook_groups_sd")
    assert {"user_url", "user_username_raw", "profile_id", "user_is_verified"} <= set(t["drop_fields"])
    groups = __import__("yaml").safe_load((ROOT / "sources/facebook_groups/groups.yaml").read_text())["groups"]
    assert all(g["url"] is None or g["url"].startswith("https://www.facebook.com/groups/") for g in groups)
