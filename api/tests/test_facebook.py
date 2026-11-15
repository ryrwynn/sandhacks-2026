"""Facebook group listings (morning run): privacy, skipped groups, reposts, medians, source breakdown, isolation.

No network and no database: Bright Data rows are dicts, Gemini is a stub, and a small fake connection
mimics the handful of statements worker.facebook issues.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api import db
from api.main import app
from api.routers import tracker
from worker import facebook as fb
from worker import train

client = TestClient(app)
T0 = datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc)
GROUP = {"url": "https://www.facebook.com/groups/apartments.sd/", "name": "SD Apartments", "zips": [],
         "locality": "San Diego (county-wide)"}
G = {**GROUP, "slug": "apartments.sd", "url_hash": "h-sd", "display_name": "SD Apartments"}
G2 = {"url": "https://www.facebook.com/groups/2387457222/", "slug": "2387457222", "url_hash": "h-ucsd",
      "display_name": "UCSD Housing", "zips": ["92122", "92037"], "locality": "UTC"}
G3 = {"url": "https://www.facebook.com/groups/797964597054309/", "slug": "797964597054309", "url_hash": "h-sub",
      "display_name": "SD Sublets", "zips": [], "locality": "San Diego"}
AUTHOR = "Maria Gonzalez"
PROFILE = "https://www.facebook.com/maria.gonzalez.4417"
PHONE = "619-555-0142"
EMAIL = "maria@example.com"
POST_TEXT = (f"2BR 1BA in North Park! $2,750/mo, available Dec 1. Parking + laundry. Contact {AUTHOR.split()[0]} "
             f"at {PHONE} or {EMAIL}")


def post(i, text=POST_TEXT, group=G, when=T0):
    return {"post_id": f"10{i}", "url": f"https://www.facebook.com/groups/{group['slug']}/posts/10{i}/?__cft__=x",
            "content": text, "date_posted": when.isoformat(), "group_url": group["url"],
            "group_name": group["display_name"], "user_url": PROFILE, "user_username_raw": AUTHOR,
            "profile_id": "100004417", "user_is_verified": False, "attachments": [{"url": "https://scontent/x.jpg"}],
            "likes": 3}


def answer(i, **kw):
    base = {"i": i, "is_rental_offer": True, "price_usd": 2750, "beds": 2, "baths": 1, "unit_type": "entire_unit",
            "neighborhood": "North Park", "zip": None, "available_date": "2026-12-01", "pets_allowed": None,
            "parking": True, "laundry": True, "utilities_included": None}
    return {**base, **kw}


class FakeConn:
    """Enough of psycopg for worker.facebook: listings, observations, raw records, fb_groups, in memory."""

    def __init__(self, median=None):
        self.sql: list[tuple[str, object]] = []
        self.listings: dict[int, dict] = {}
        self.obs: list[dict] = []
        self.raw: list[dict] = []
        self.groups: dict[str, dict] = {}
        self.median = median
        self._next = 1
        self._one = None
        self._all = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        self._one, self._all = None, []
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO raw_records"):
            self.raw.append(json.loads(params[3]))
            self._one = (len(self.raw),)
        elif s.startswith("INSERT INTO fb_groups"):
            self.groups[params[0]] = {"display_name": params[1], "is_public": params[4], "last": params[5]}
        elif "DISTINCT ON (po.listing_id) po.price_usd FROM price_observations" in s:
            self._all = [(self.median,)] * 5 if self.median else []
        elif s.startswith("SELECT listing_id, extras FROM"):
            _, key, posted, days, posted2, _ = params
            hits = [l for l in self.listings.values() if l["extras"]["dedupe_key"] == key
                    and l["last_seen"] >= posted - timedelta(days=days) and l["first_seen"] <= posted2 + timedelta(days=days)]
            hits.sort(key=lambda l: l["last_seen"], reverse=True)
            self._one = (hits[0]["id"], hits[0]["extras"]) if hits else None
        elif s.startswith("SELECT price_usd FROM"):
            lid, when = params
            prev = sorted((o for o in self.obs if o["listing_id"] == lid and o["observed_at"] <= when),
                          key=lambda o: o["observed_at"])
            self._one = (prev[-1]["price_usd"],) if prev else None
        elif s.startswith("SELECT last_seen <="):
            when, lid = params
            self._one = (self.listings[lid]["last_seen"] <= when,)
        elif s.startswith("UPDATE"):
            l = self.listings[params["id"]]
            l["last_seen"] = max(l["last_seen"], params["t"])
            l["first_seen"] = min(l["first_seen"], params["t"])
            l["extras"] = {**l["extras"], **json.loads(params["x"])}
        elif s.startswith("INSERT INTO staging_listings") or s.startswith("INSERT INTO listings"):
            lid = self._next
            self._next += 1
            self.listings[lid] = {"id": lid, "property_id": params[2], "zip": params[4], "beds": params[7],
                                  "text": params[10], "extras": json.loads(params[11]), "first_seen": params[14],
                                  "last_seen": params[15], "table": s.split()[2]}
            self._one = (lid,)
        elif "price_observations" in s and s.startswith("INSERT"):
            when, lid, src, z, beds, price, trust, event = params
            if not any(o["listing_id"] == lid and o["observed_at"] == when and o["event"] == event for o in self.obs):
                self.obs.append({"listing_id": lid, "observed_at": when, "price_usd": price, "trust": trust,
                                 "event": event, "table": s.split()[2]})
        return self

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def commit(self):
        pass


def stub_parse(answers):
    calls = []

    def parse(texts, today):
        calls.append(list(texts))
        return [answers(i, t) for i, t in enumerate(texts)]
    parse.calls = calls
    return parse


def run(rows, groups, answers, conn=None):
    conn = conn or FakeConn()
    parse = stub_parse(answers)
    stats = fb.process(conn, rows, groups, "staging", parse=parse, sleep=lambda s: None, today="2026-11-15")
    offers = stats.pop("offers")
    fb.load_offers(conn, offers, "staging")
    return conn, stats, parse


# ---------------------------------------------------------------- privacy
def written_values(conn) -> str:
    out = []
    for sql, params in conn.sql:
        vals = params.values() if isinstance(params, dict) else (params or ())
        out += [json.dumps(v, default=str) if not isinstance(v, str) else v for v in vals]
    return "\n".join(out)


def test_no_personal_fields_or_post_text_are_stored():
    conn, stats, parse = run([post(1)], [G], lambda i, t: answer(i))
    assert stats["usable"] == 1
    blob = written_values(conn)
    for secret in (AUTHOR, AUTHOR.split()[0], PROFILE, PHONE, EMAIL, "100004417", "scontent", "Parking + laundry",
                   "__cft__"):
        assert secret not in blob, secret
    for forbidden in ("user_url", "user_username_raw", "profile_id", "attachments", "content", "text"):
        assert all(forbidden not in r for r in conn.raw)
    (l,) = conn.listings.values()
    assert l["text"] is None and l["property_id"] is None
    assert l["extras"]["post_url"] == "https://www.facebook.com/groups/apartments.sd/posts/101/"


def test_text_sent_to_gemini_is_redacted():
    _, _, parse = run([post(1)], [G], lambda i, t: answer(i))
    sent = parse.calls[0][0]
    assert PHONE not in sent and EMAIL not in sent and AUTHOR.split()[0] not in sent


def test_post_url_only_accepts_group_posts():
    assert fb.clean_post_url(PROFILE) is None
    assert fb.clean_post_url("https://www.facebook.com/profile.php?id=4417") is None
    assert fb.clean_post_url("https://www.facebook.com/photo/?fbid=1") is None
    assert fb.clean_post_url("https://www.facebook.com/groups/abc/permalink/123/?x=1") == \
        "https://www.facebook.com/groups/abc/posts/123/"


def fb_row(**kw):
    base = {"listing_id": 77, "zip": "92104", "listing_type": "rent", "beds": 2, "baths": 1, "sqft": None,
            "last_seen": T0, "address_norm": "2519 el cajon blvd", "unit_label": "210", "property_type": None,
            "year_built": 1965, "source_kind": "social", "source_key": "facebook_groups_sd",
            "location_precision": "zip", "post_neighborhood": "North Park", "source_url": PROFILE, "active": True,
            "unit_type": "entire_unit", "post_url": "https://www.facebook.com/groups/apartments.sd/posts/101/",
            "group_name": "SD Apartments", "posted_at": T0.isoformat(), "available_date": "2026-12-01",
            "amenities": ["parking"], "unusual_price": False, "n": 1, "cur": 2750, "first_price": 2750,
            "first_observed": T0.date(), "total": 1,
            # columns a careless query might add: they must never reach a response
            "text_redacted": POST_TEXT, "user_name": AUTHOR, "user_url": PROFILE, "content": POST_TEXT}
    return {**base, **kw}


def test_api_responses_never_contain_post_text_author_or_profile(monkeypatch):
    monkeypatch.setattr(db, "listing_page", lambda *a, **k: [fb_row()])
    monkeypatch.setattr(db, "listing_observations", lambda ids: [
        {"listing_id": 77, "observed_at": T0, "event": "posted", "price_usd": 2750}])
    monkeypatch.setattr(tracker, "group_label", lambda *a: "in_range")
    monkeypatch.setattr(tracker, "estimate", lambda row: (None, [], {}))
    monkeypatch.setattr(tracker, "_forecast_summary", lambda z: None)
    for url in ("/listings?source=facebook", "/listings/77"):
        r = client.get(url)
        assert r.status_code == 200, r.text
        body = r.text
        for secret in (AUTHOR, PROFILE, PHONE, EMAIL, "Parking + laundry", "el cajon", "El Cajon"):
            assert secret not in body, (url, secret)
        j = r.json()
        item = j["items"][0] if "items" in j else j
        assert item["address"] is None and item["unit_label"] is None and item["source_url"] is None
        assert item["source_label"] == "Facebook group" and item["post_url"].startswith("https://www.facebook.com/groups/")
        assert item["year_built"] is None if "year_built" in item else True


# ---------------------------------------------------------------- skipped groups
def test_group_with_nothing_or_access_error_is_skipped():
    err = {"input": {"url": G2["url"]}, "error": "Login required to view this group", "error_code": "login"}
    conn, stats, parse = run([err, post(1)], [G, G2, G3], lambda i, t: answer(i))
    skipped = {s["name"]: s["reason"] for s in stats["groups_skipped"]}
    assert set(skipped) == {"UCSD Housing", "SD Sublets"}
    assert conn.groups["h-ucsd"]["is_public"] is False        # access error
    assert conn.groups["h-sub"]["is_public"] is None          # returned nothing
    assert conn.groups["h-sd"]["is_public"] is True
    assert len(parse.calls) == 1 and len(parse.calls[0]) == 1  # only the public group's post went to Gemini


# ---------------------------------------------------------------- reposts
def test_reposts_become_price_observations_on_one_listing():
    rows = [post(1, when=T0), post(2, POST_TEXT.replace("$2,750", "$2,650"), when=T0 + timedelta(days=6)),
            post(3, POST_TEXT.replace("$2,750", "$2,650"), when=T0 + timedelta(days=12))]
    prices = {0: 2750, 1: 2650, 2: 2650}
    conn, stats, _ = run(rows, [G], lambda i, t: answer(i, price_usd=prices[i]))
    assert len(conn.listings) == 1
    (l,) = conn.listings.values()
    events = [(o["event"], o["price_usd"]) for o in sorted(conn.obs, key=lambda o: o["observed_at"])]
    assert events == [("posted", 2750), ("price_change", 2650), ("posted", 2650)]
    assert all(o["trust"] == 0.5 and o["table"] == "staging_price_observations" for o in conn.obs)
    assert l["last_seen"] == T0 + timedelta(days=12) and l["first_seen"] == T0
    assert l["table"] == "staging_listings"


def test_same_post_twice_adds_nothing_and_a_late_repost_is_a_new_listing():
    conn, _, _ = run([post(1)], [G], lambda i, t: answer(i))
    run([post(1)], [G], lambda i, t: answer(i), conn=conn)                          # same post again
    assert len(conn.listings) == 1 and len(conn.obs) == 1
    run([post(9, when=T0 + timedelta(days=45))], [G], lambda i, t: answer(i), conn=conn)
    assert len(conn.listings) == 2                                                  # outside the 30-day window


def test_shared_target_takes_core_zips_only():
    conn = FakeConn()
    o = {"post_id_hash": "p1", "post_url": None, "group_hash": "g", "group_name": "g", "date_posted": T0.isoformat(),
         "text_hash": "t", "price_usd": 2000, "beds": 1, "baths": None, "unit_type": "entire_unit", "zip": "92037",
         "zip_from": "post", "neighborhood": None, "available_date": None, "amenities": []}
    res = fb.load_offers(conn, [o, {**o, "post_id_hash": "p2", "text_hash": "u", "zip": "92104"}], "shared")
    assert res["staged_outside_core"] == 1
    tables = sorted(l["table"] for l in conn.listings.values())
    assert tables == ["listings", "staging_listings"]


# ---------------------------------------------------------------- medians
def test_rooms_and_unusual_prices_never_enter_whole_unit_medians():
    assert "l.extras->>'unit_type' = 'entire_unit'" in db.MEDIAN_SOURCES
    assert "unusual_price" in db.MEDIAN_SOURCES
    rows = [{"kind": "listing_site", "source_key": "zillow_rent", "unit_type": None, "unusual": False, "cur": c, "w": 1}
            for c in (2400, 2600, 2800)]
    rows += [{"kind": "social", "source_key": "facebook_groups_sd", "unit_type": "room", "unusual": False, "cur": 900, "w": .5},
             {"kind": "social", "source_key": "facebook_groups_sd", "unit_type": "sublet", "unusual": False, "cur": 1100, "w": .5},
             {"kind": "social", "source_key": "facebook_groups_sd", "unit_type": "entire_unit", "unusual": True, "cur": 400, "w": .5},
             {"kind": "social", "source_key": "facebook_groups_sd", "unit_type": "entire_unit", "unusual": False, "cur": 2500, "w": .5}]
    b = tracker.source_breakdown(rows)
    assert b.facebook.count == 2 and b.facebook.median_usd == 2500       # the $400 one is counted, not in the median
    assert b.facebook_rooms.count == 2 and b.facebook_unusual == 1
    assert b.listing_sites.median_usd == 2600


def test_unusual_price_thresholds_and_weighted_median():
    assert fb.is_unusual(900, 2500) and fb.is_unusual(6300, 2500)
    assert not fb.is_unusual(1000, 2500) and not fb.is_unusual(6250, 2500) and not fb.is_unusual(10, None)
    # Facebook at half weight: two 0.5 rows weigh as much as one listing-site row
    assert db.weighted_median([(2000, 1), (3000, .5), (3000, .5)]) == 2500
    assert db.weighted_median([(2000, 1), (2200, 1), (3000, .5)]) == 2200


def test_unusual_flag_only_for_whole_units():
    conn = FakeConn(median=2500)
    o = {"post_id_hash": "p", "post_url": None, "group_hash": "g", "group_name": "g", "date_posted": T0.isoformat(),
         "text_hash": "t", "price_usd": 800, "beds": 1, "baths": None, "unit_type": "room", "zip": "92104",
         "zip_from": "post", "neighborhood": None, "available_date": None, "amenities": []}
    fb.load_offers(conn, [o, {**o, "post_id_hash": "q", "text_hash": "v", "unit_type": "entire_unit"}], "staging")
    flags = sorted((l["extras"]["unit_type"], l["extras"]["unusual_price"]) for l in conn.listings.values())
    assert flags == [("entire_unit", True), ("room", False)]


# ---------------------------------------------------------------- market breakdown
def _market_rows():
    ls = [{"kind": "listing_site", "source_key": "zillow_rent", "unit_type": None, "unusual": False, "cur": 2600, "w": 1}] * 10
    fbr = [{"kind": "social", "source_key": "facebook_groups_sd", "unit_type": u, "unusual": un, "cur": c, "w": .5}
           for u, un, c in (("entire_unit", False, 2500), ("entire_unit", True, 7000), ("room", False, 1200))]
    return ls + fbr


def test_market_source_breakdown_adds_up(monkeypatch):
    monkeypatch.setattr(db, "zori_monthly", lambda z: [])
    monkeypatch.setattr(db, "forecast_latest", lambda z: [])
    monkeypatch.setattr(db, "last_scrape_at", lambda: T0)
    monkeypatch.setattr(db, "active_by_source", lambda z, b, t: _market_rows())
    j = client.get("/market?zip=92104").json()
    s = j["sources"]
    assert s["listing_sites"]["count"] + s["facebook"]["count"] + s["facebook_rooms"]["count"] == len(_market_rows())
    assert j["active_listings"] == s["listing_sites"]["count"] + s["facebook"]["count"] == 12
    j2 = client.get("/market?zip=92104&listing_sites_only=true").json()
    assert j2["active_listings"] == 10 and j2["listing_sites_only"] is True and j2["sources"]["listing_sites_only"]


# ---------------------------------------------------------------- isolation
def test_facebook_rows_never_train_fair_rent():
    sql = " ".join(train.RENTALS_SQL.split())
    assert "JOIN properties p ON p.property_id = l.property_id" in sql and "LEFT JOIN properties" not in sql
    assert "l.location_precision = 'address'" in sql and "NOT LIKE 'facebook%%'" in sql


def test_facebook_rows_never_create_building_facts():
    conn, _, _ = run([post(1), post(2, when=T0 + timedelta(days=3))], [G], lambda i, t: answer(i))
    assert not any(re.search(r"\bproperties\b", s) for s, _ in conn.sql)
    assert all(l["property_id"] is None for l in conn.listings.values())


def test_facebook_listing_never_feeds_building_facts_or_ab1482(monkeypatch):
    seen = {}
    monkeypatch.setattr(db, "listing_page", lambda *a, **k: [fb_row()])
    monkeypatch.setattr(db, "listing_observations", lambda ids: [])
    monkeypatch.setattr(db, "listing_coords", lambda i: (_ for _ in ()).throw(AssertionError("coords read")))
    monkeypatch.setattr(tracker, "_forecast_summary", lambda z: None)
    monkeypatch.setattr(tracker, "group_label", lambda *a: None)

    def fake_estimate(row):
        seen.update(row)
        return {"low": 2300, "expected": 2600, "high": 2900, "method": "zip_bed_median"}, [2500, 2600, 2700], {}
    monkeypatch.setattr(tracker, "estimate", fake_estimate)
    j = client.get("/listings/77").json()
    assert seen["zip"] == "92104" and seen["beds"] == 2
    assert seen["year_built"] is None and seen["sqft"] is None and seen["lat"] is None   # ZIP and beds only
    assert j["year_built"] is None and j["fair_rent_label"] == "in_range" and j["estimate"]["expected"] == 2600
    # the AB 1482 check finds buildings only through properties, which Facebook rows never write
    src = open(db.__file__).read()
    assert "FROM properties WHERE address_norm ILIKE" in src


def test_rooms_get_no_fair_rent_label(monkeypatch):
    monkeypatch.setattr(db, "listing_page", lambda *a, **k: [fb_row(unit_type="room", cur=1200, first_price=1200)])
    monkeypatch.setattr(db, "listing_observations", lambda ids: [])
    monkeypatch.setattr(tracker, "group_label", lambda *a: "in_range")
    item = client.get("/listings?source=facebook&unit_type=room").json()["items"][0]
    assert item["unit_type"] == "room" and item["fair_rent_label"] is None


# ---------------------------------------------------------------- extraction validation
def test_validation_keeps_offers_with_price_beds_and_zip_only():
    zips, hoods = fb.sd_zips(), fb.neighborhood_table()
    p = {"post_id": "1", "url": None, "text": "Room in a 3br house near SDSU, $950", "date_posted": T0.isoformat()}
    assert fb.validate(p, answer(0, unit_type="room", beds=1, price_usd=950, neighborhood="SDSU"), G, zips, hoods)[0]["zip"] == "92115"
    assert fb.validate(p, answer(0, is_rental_offer=False), G, zips, hoods)[1] == "not_offer"
    assert fb.validate(p, answer(0, neighborhood="Carlsbad"), G, zips, hoods)[1] == "no_zip"   # multi-ZIP city
    # a ZIP Gemini returns must be written in the post
    assert fb.validate(p, answer(0, neighborhood=None, zip="92104"), G, zips, hoods)[1] == "no_zip"
    assert fb.validate(p, answer(0, price_usd=None), G, zips, hoods)[1] == "no_price_or_beds"
    assert fb.validate(p, None, G, zips, hoods)[1] == "no_answer"


def test_one_bad_item_does_not_sink_the_batch():
    rows = [post(i, POST_TEXT + f" #{i}") for i in range(12)]

    def answers(i, t):
        return {"i": i, "price_usd": "lots"} if i == 3 else answer(i)
    conn, stats, parse = run(rows, [G], answers)
    assert [len(c) for c in parse.calls] == [10, 2]
    assert stats["usable"] == 11
