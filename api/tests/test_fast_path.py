"""Sprint D1: the fast path (worker.fast) and the row-by-row path give identical staging rows.

No network and no database: the same 200 records go through (a) bd cleaner + process_listing_payloads +
replay.staging_args and (b) worker.fast.process_chunk in chunks. Gemini is not called (budget 0).
Opt-in database checks (RUN_DB_TESTS=1 with DATABASE_URL) live in test_fast_path_db.py.
"""
import copy
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import orjson
import pytest

from worker import fast
from worker.bd import _Cleaner
from worker.clean import content_hash
from worker.llm_extract import LlmBudget
from worker.mapping import load_template
from worker.replay import staging_args
from worker.run import process_listing_payloads

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "contracts" / "fixtures" / "sources" / "zillow_rent"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
KEY = "zillow_rent_county"


def county_zips():
    return [ln.split(",")[0] for ln in (ROOT / "data" / "zips_county.txt").read_text().splitlines()[1:]][:30]


def make_records(n=200, seed=7):
    """200 Zillow-shaped records: fixture rows varied the way real exports vary (string prices, studios,
    units, odd statuses, missing ids, non-ASCII text, contacts in the description, shared building history)."""
    rnd = random.Random(seed)
    base = [json.loads(p.read_text()) for p in sorted(FIX.glob("rec*.json"))]
    zips = county_zips()
    streets = ["Main Street", "N Park Boulevard", "El Cajon Blvd", "Ocean Avenue", "5th Ave.", "Via de la Valle"]
    out = []
    for i in range(n):
        r = copy.deepcopy(rnd.choice(base))
        r["zpid"] = 9000 + i
        r["zipcode"] = rnd.choice(zips) + ("-1234" if i % 17 == 0 else "")
        street = f"{rnd.randint(10, 9999)} {rnd.choice(streets)}"
        r["streetAddress"] = street + rnd.choice(["", " Apt 4B", ", Unit 12", " #7", " Suite 300"])
        r["unit_number"] = rnd.choice([None, "Unit 210", "APT 535", "#12", 14, ""])
        price = rnd.choice([1800, 2395, 3100, 4200.0, "$2,350", "2,100/mo", None, 0])
        r["price"], r["base_rent"] = price, None if i % 5 else 2500
        r["bedrooms"] = rnd.choice([0, 1, 2, 3, "Studio", "2 bd", 1.0, None])
        r["bathrooms"] = rnd.choice([1, 1.5, 2, "2.5", None])
        r["sqft"] = rnd.choice([450, 700, "1,050", None])
        r["homeType"] = rnd.choice(["APARTMENT", "CONDO", "SINGLE_FAMILY", "TOWNHOUSE", "LOT", None])
        r["homeStatus"] = "FOR_RENT" if i % 11 else rnd.choice(["SOLD", "FOR_SALE"])
        r["latitude"] = rnd.choice([32.75, 33.1, None, 0.0])
        r["description"] = rnd.choice([
            "Call Maria Lopez at (619) 555-0182 or email maria@example.com, see https://x.example/y. Built in 1985.",
            "Sunny unit near the beach — cafés nearby. Contact Mr. Lee for a tour.", None, "", "Quiet street."])
        r["days_on_zillow"] = rnd.choice([None, 3, 40])
        if i % 13 == 0:
            r["zpid"] = None
        if i % 23 == 0:
            r["zipcode"] = "99999"                       # outside the county list
        if i % 7 == 0:
            r["priceHistory"] = base[0]["priceHistory"]  # same history on several units of one address
            r["streetAddress"] = "2020 El Cajon Blvd"
        if i % 19 == 0:
            r["priceHistory"] = None
        out.append(r)
    out.append({"error": "dead_page", "input": {"url": "x"}})
    return out


@pytest.fixture(scope="module")
def records():
    return make_records()


@pytest.fixture(scope="module")
def slow(records):
    t = load_template(KEY)
    cleaner = _Cleaner(t)
    payloads = [cleaner.clean_payload(r) for r in records if isinstance(r, dict) and not r.get("error")]
    tt = dict(t, source_key=t["loads_as"])
    listings, _ = process_listing_payloads(tt, payloads, NOW, LlmBudget(0))
    return {l.external_id_hash: staging_args(l, 1.0, None) for l in listings}, payloads


def jn(v):
    return json.loads(json.dumps(v, default=str))


def fast_rows(records, size=37):
    """The fast path over chunks (uneven size on purpose), with the end-of-run building-level step."""
    lines = [orjson.dumps(r) for r in records]
    rows, hist = [], []
    for ch in fast.chunk_lines(lines, size):
        res = fast.process_chunk(KEY, ch, NOW.isoformat(), 1.0)
        rows += res["rows"]
        hist += res["hist"]
    return fast.strip_building_level(rows, fast.building_level(hist)), hist


def test_fast_and_slow_paths_produce_identical_staging_rows(records, slow):
    slow_rows, _ = slow
    rows, _ = fast_rows(records)
    got = {r[1]: r for r in rows}
    assert len(rows) == len(got) > 100
    assert set(got) == set(slow_rows)
    for ext, srow in slow_rows.items():
        f = got[ext]
        assert f[:10] == srow[:10], ext
        assert jn(f[10]) == jn(srow[10]), ext            # extras
        assert jn(f[11]) == jn(srow[11]), ext            # field_confidence
        assert f[12:] == srow[12:], ext                  # extraction, price, observed_at, raw_record_id


def test_chunk_size_does_not_change_the_result(records):
    a, _ = fast_rows(records, 2000)
    b, _ = fast_rows(records, 9)
    key = lambda r: r[1]
    assert [jn(r) for r in sorted(a, key=key)] == [jn(r) for r in sorted(b, key=key)]


def test_raw_payloads_and_content_hashes_match_the_current_path(records, slow):
    _, payloads = slow
    t = load_template(KEY)
    lines = [orjson.dumps(r) for r in records]
    res = fast.process_chunk(KEY, lines, NOW.isoformat(), 1.0)
    want = {content_hash(p, t.get("hash_ignore")): p for p in payloads}
    got = {h: orjson.loads(b) for h, b in res["raw"]}
    assert set(got) == set(want)
    assert all(jn(got[h]) == jn(want[h]) for h in want)
    assert res["billed"] == len(records) and res["errors"] == 1      # the error row is billed, not mapped


def test_personal_fields_never_reach_raw_or_staging(records):
    lines = [orjson.dumps(r) for r in records]
    res = fast.process_chunk(KEY, lines, NOW.isoformat(), 1.0)
    blob = b"".join(b for _, b in res["raw"]).decode() + json.dumps([r[9] for r in res["rows"]])
    assert "(619) 555-0182" not in blob and "maria@example.com" not in blob and "Maria Lopez" not in blob
    assert "management_company_phone_number" not in blob and "listing_provided_by" not in blob


def test_building_level_history_is_dropped_across_chunks(records, slow):
    rows, hist = fast_rows(records, 5)
    bl = fast.building_level(hist)
    assert bl                                             # units of one building share a history
    by = {r[1]: r for r in rows}
    assert all("price_history" not in by[e][10] for e in bl if e in by)
    assert any("price_history" in r[10] for r in rows)    # a unit's own history stays


def test_hash_partition_is_stable_and_in_range():
    seen = {fast.part_of(hashlib.sha256(str(i).encode()).hexdigest(), 4) for i in range(500)}
    assert seen == {0, 1, 2, 3}
    assert fast.part_of("ab" * 32, 4) == fast.part_of("ab" * 32, 4)


def test_worker_procs_env(monkeypatch):
    monkeypatch.setenv("WORKER_PROCS", "3")
    assert fast.default_procs() == 3
    monkeypatch.delenv("WORKER_PROCS")
    assert 1 <= fast.default_procs() <= 8
