"""Facebook rental groups -> listings with price history (source facebook_groups_sd). Reads only.

uv run python -m worker.facebook sample                 # 20 posts from each of the first two groups, gated
uv run python -m worker.facebook collect [--limit 50]   # every group in sources/facebook_groups/groups.yaml
uv run python -m worker.facebook replay --target shared --confirm-shared   # staged raw records -> live tables
add --cron to refuse unless sources.terms_checked_on is set (the scheduled job always passes it)

Pipeline: one batched Bright Data trigger (cap = groups x limit; a snapshot that reports more records than
its cap is cancelled) -> keep only post_id, post URL, text, date and group fields (author fields, names,
profile links and photos are never read) -> redact names/phones/emails -> Gemini, about 10 posts per request,
each answer validated on its own -> rental offers with a price, beds and a San Diego ZIP -> raw_records
(fields only: post text is never stored) -> listings.

Listings: property_id NULL, location_precision 'zip', trust 0.5. The same normalized text, beds and ZIP
within 30 days is one listing; every repost is a price observation ('posted', or 'price_change' when the
price moved). A listing is inactive 21 days after its last post (computed by the API from last_seen).
Targets: staging (default) writes staging_listings / staging_price_observations; shared writes the live
tables but only for data/zips.txt ZIPs (the rest stay staged).
"""
import argparse
import csv
import hashlib
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from worker import bd, load
from worker.clean import content_hash, redact_text
from worker.mapping import ROOT, load_template

log = logging.getLogger("worker.facebook")
SOURCE = "facebook_groups_sd"
TRUST = 0.5
BATCH = 10
PAUSE_S = 4.0                   # between Gemini requests (free-tier rate limit)
SAMPLE_GROUPS, SAMPLE_PER_GROUP = 2, 20
MIN_USABLE_SHARE = 0.25
DEDUPE_DAYS = 30
INACTIVE_DAYS = 21
UNUSUAL_LO, UNUSUAL_HI = 0.40, 2.50
MIN_COMPS = 3
UNIT_TYPES = ("entire_unit", "room", "sublet")
AMENITY_FIELDS = ("pets_allowed", "parking", "laundry", "utilities_included")
# The only scraper fields ever read. Everything else (user_url, user_username_raw, profile_id, user_id,
# attachments, likes, ...) is dropped before anything else happens.
KEEP_FIELDS = ("post_id", "url", "content", "date_posted", "group_url", "group_name", "group_id", "input",
               "error", "error_code")
TABLES = {"staging": ("staging_listings", "staging_price_observations"),
          "shared": ("listings", "price_observations")}


# ---------------------------------------------------------------- reference data
def load_groups(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "sources" / "facebook_groups" / "groups.yaml"
    out = []
    for g in (yaml.safe_load(path.read_text()) or {}).get("groups", []):
        if g.get("url"):
            out.append({**g, "slug": group_slug(g["url"]), "url_hash": bd.url_hash(g["url"]),
                        "display_name": g.get("name") or g.get("locality")})
    return out


def group_slug(url: str | None) -> str | None:
    m = re.search(r"facebook\.com/groups/([^/?#]+)", url or "")
    return m.group(1).lower() if m else None


def _zip_csv(name: str) -> set[str]:
    p = ROOT / "data" / name
    return {line.split(",")[0].strip() for line in p.read_text().splitlines() if line[:1].isdigit()}


def sd_zips() -> set[str]:
    zs = _zip_csv("zips.txt") | _zip_csv("zips_county.txt")
    with (ROOT / "data" / "areas_ca.csv").open() as f:
        zs |= {r["zip"] for r in csv.DictReader(f) if r["county"] == "San Diego"}
    return zs


def core_zips() -> set[str]:
    return _zip_csv("zips.txt")


def norm_name(s: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split())


def neighborhood_table() -> dict[str, str]:
    out = {}
    for line in (ROOT / "data" / "fb_neighborhood_zips.csv").read_text().splitlines()[1:]:
        if line.startswith("#") or "," not in line:
            continue
        name, z = line.split(",")[:2]
        out[norm_name(name)] = z.strip()
    return out


# ---------------------------------------------------------------- cleaning
POST_URL = re.compile(r"^https://(?:www\.|m\.|web\.)?facebook\.com/groups/([A-Za-z0-9.\-_]+)/"
                      r"(?:posts|permalink)/(\d+)")


def clean_post_url(url: str | None) -> str | None:
    """Canonical public post link with no query string (tracking ids); anything else (profile links,
    photos, user pages) is refused."""
    m = POST_URL.match(url or "")
    return f"https://www.facebook.com/groups/{m.group(1)}/posts/{m.group(2)}/" if m else None


def normalize_text(text: str | None) -> str:
    """For dedupe only: lowercase, prices and long numbers removed (a price change keeps the key)."""
    t = (text or "").lower()
    t = re.sub(r"\$\s?[\d,]+(?:\.\d+)?k?", " ", t)
    t = re.sub(r"\d{3,}", " ", t.replace(",", ""))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def whitelist(row: dict) -> dict:
    return {k: row[k] for k in KEEP_FIELDS if k in row}


def _row_slug(row: dict) -> str | None:
    for u in ((row.get("input") or {}).get("url"), row.get("group_url"), row.get("url")):
        s = group_slug(u)
        if s:
            return s
    gid = row.get("group_id")
    return str(gid).lower() if gid else None


def split_by_group(raw_rows: list[dict], groups: list[dict]) -> tuple[dict, dict]:
    """(posts by slug, errors by slug). Rows are whitelisted first; unmatched rows are ignored."""
    by_slug = {g["slug"]: g for g in groups}
    posts: dict[str, list] = {s: [] for s in by_slug}
    errors: dict[str, list] = {s: [] for s in by_slug}
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        r = whitelist(r)
        s = _row_slug(r)
        if s not in by_slug:
            continue
        if r.get("error") or r.get("error_code") or not r.get("content"):
            errors[s].append(str(r.get("error") or r.get("error_code") or "empty post")[:120])
        else:
            posts[s].append(r)
    return posts, errors


def parse_date(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- extraction
def extract(posts: list[dict], today: str, parse=None, sleep=time.sleep, max_requests: int = 60) -> list:
    """[(post, fields or None)] with post['text'] redacted. One Gemini request per BATCH posts."""
    if parse is None:
        from api.llm.gemini import parse_posts as parse
    out = []
    for p in posts:
        p["text"] = redact_text(p.get("content") or "")
        p.pop("content", None)
    for n, start in enumerate(range(0, len(posts), BATCH)):
        chunk = posts[start:start + BATCH]
        if n >= max_requests:
            out += [(p, None) for p in chunk]
            continue
        if n:
            sleep(PAUSE_S)
        items = parse([p["text"] for p in chunk], today) or []
        by_i = {}
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("i"), int):
                by_i.setdefault(it["i"], it)
        out += [(p, by_i.get(i)) for i, p in enumerate(chunk)]
    return out


def _int(v, lo, hi):
    try:
        x = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def resolve_zip(fields: dict, text: str, group: dict, zips: set[str], hoods: dict[str, str]) -> tuple[str | None, str]:
    z = str(fields.get("zip") or "").strip()[:5]
    if z in zips and z in text:                         # a ZIP Gemini read must be written in the post
        return z, "post"
    hz = hoods.get(norm_name(fields.get("neighborhood")))
    if hz:
        return hz, "neighborhood"
    gz = [x for x in group.get("zips") or [] if x in zips]
    if len(gz) == 1:
        return gz[0], "group"
    return None, "none"


def validate(post: dict, fields: dict | None, group: dict, zips: set[str], hoods: dict[str, str]) -> tuple[dict | None, str]:
    """One post's Gemini answer -> an offer dict, or (None, reason)."""
    if not fields:
        return None, "no_answer"
    if fields.get("is_rental_offer") is not True:
        return None, "not_offer"
    price = _int(fields.get("price_usd"), 300, 15000)
    beds = _int(fields.get("beds"), 0, 8)
    unit = fields.get("unit_type")
    if price is None or beds is None:
        return None, "no_price_or_beds"
    if unit not in UNIT_TYPES:
        return None, "no_unit_type"
    posted = parse_date(post.get("date_posted"))
    if posted is None:
        return None, "no_date"
    z, how = resolve_zip(fields, post["text"], group, zips, hoods)
    if z is None:
        return None, "no_zip"
    try:
        baths = float(fields["baths"]) if fields.get("baths") is not None else None
        baths = baths if baths is not None and 0 < baths <= 8 else None
    except (TypeError, ValueError):
        baths = None
    avail = fields.get("available_date")
    try:
        avail = date.fromisoformat(str(avail)).isoformat() if avail else None
    except ValueError:
        avail = None
    hood = redact_text((fields.get("neighborhood") or "").strip()[:60]) or None
    amen = [k for k in AMENITY_FIELDS if fields.get(k) is True]
    return {
        "post_id_hash": sha(str(post.get("post_id") or post.get("url") or post["text"][:200])),
        "post_url": clean_post_url(post.get("url")),
        "group_hash": group["url_hash"], "group_name": group["display_name"],
        "date_posted": posted.isoformat(), "text_hash": sha(normalize_text(post["text"])),
        "price_usd": price, "beds": beds, "baths": baths, "unit_type": unit, "zip": z, "zip_from": how,
        "neighborhood": hood, "available_date": avail, "amenities": amen,
    }, "ok"


# ---------------------------------------------------------------- loading
def dedupe_key(o: dict) -> str:
    return sha(f"{o['text_hash']}|{o['beds']}|{o['zip']}")


def listing_site_median(conn, zip_: str, beds: int) -> float | None:
    rows = conn.execute(
        "SELECT DISTINCT ON (po.listing_id) po.price_usd FROM price_observations po "
        "JOIN sources s ON s.source_key = po.source_key WHERE s.kind = 'listing_site' AND po.listing_type = 'rent' "
        "AND po.zip = %s AND po.beds = %s AND po.event <> 'removed' AND po.observed_at >= now() - interval '90 days' "
        "ORDER BY po.listing_id, po.observed_at DESC", (zip_, beds)).fetchall()
    prices = sorted(float(r[0]) for r in rows)
    if len(prices) < MIN_COMPS:
        return None
    m = len(prices) // 2
    return prices[m] if len(prices) % 2 else (prices[m - 1] + prices[m]) / 2


def is_unusual(price: float, median: float | None) -> bool:
    return median is not None and not (UNUSUAL_LO * median <= price <= UNUSUAL_HI * median)


def upsert_offer(conn, o: dict, target: str, median=listing_site_median) -> str:
    """'new' | 'repost' | 'seen'. Call in date order so 'price_change' compares with the previous post."""
    L, PO = TABLES[target]
    key = dedupe_key(o)
    posted = parse_date(o["date_posted"])
    unusual = o["unit_type"] == "entire_unit" and is_unusual(o["price_usd"], median(conn, o["zip"], o["beds"]))
    row = conn.execute(
        f"SELECT listing_id, extras FROM {L} WHERE source_key = %s AND extras->>'dedupe_key' = %s "
        "AND last_seen >= %s - make_interval(days => %s) AND first_seen <= %s + make_interval(days => %s) "
        "ORDER BY last_seen DESC LIMIT 1", (SOURCE, key, posted, DEDUPE_DAYS, posted, DEDUPE_DAYS)).fetchone()
    extras = {"unit_type": o["unit_type"], "amenities": o["amenities"], "group_name": o["group_name"],
              "group_hash": o["group_hash"], "post_url": o["post_url"], "available_date": o["available_date"],
              "dedupe_key": key, "unusual_price": unusual, "trust_weight": TRUST, "zip_from": o["zip_from"],
              "posted_at": o["date_posted"]}
    if row:
        lid, old = row
        hashes = list((old or {}).get("post_hashes") or [])
        if o["post_id_hash"] in hashes:
            return "seen"
        prev = conn.execute(f"SELECT price_usd FROM {PO} WHERE listing_id = %s AND observed_at <= %s "
                            "ORDER BY observed_at DESC LIMIT 1", (lid, posted)).fetchone()
        event = "posted" if prev is None or int(prev[0]) == o["price_usd"] else "price_change"
        extras["post_hashes"] = hashes + [o["post_id_hash"]]
        newer = conn.execute(f"SELECT last_seen <= %s FROM {L} WHERE listing_id = %s", (posted, lid)).fetchone()[0]
        if not newer:          # an older repost adds history but doesn't replace the latest post's facts
            extras = {"post_hashes": extras["post_hashes"]}
        extra_cols = ", price_usd = %(p)s, observed_at = %(t)s" if target == "staging" and newer else ""
        conn.execute(f"UPDATE {L} SET last_seen = greatest(last_seen, %(t)s), first_seen = least(first_seen, %(t)s), "
                     f"extras = extras || %(x)s::jsonb{extra_cols} WHERE listing_id = %(id)s",
                     {"t": posted, "x": json.dumps(extras), "p": o["price_usd"], "id": lid})
        status = "repost"
    else:
        extras["post_hashes"] = [o["post_id_hash"]]
        cols = ("source_key, external_id_hash, property_id, listing_type, zip, neighborhood, location_precision, "
                "beds, baths, sqft, text_redacted, extras, field_confidence, extraction, first_seen, last_seen")
        vals = [SOURCE, sha(key + o["post_id_hash"]), None, "rent", o["zip"], o["neighborhood"], "zip", o["beds"],
                o["baths"], None, None, json.dumps(extras), json.dumps({}), "llm", posted, posted]
        if target == "staging":
            cols += ", price_usd, observed_at"
            vals += [o["price_usd"], posted]
        ph = ",".join(["%s"] * len(vals))
        lid = conn.execute(f"INSERT INTO {L} ({cols}) VALUES ({ph}) ON CONFLICT (source_key, external_id_hash) "
                           "DO UPDATE SET last_seen = EXCLUDED.last_seen RETURNING listing_id", vals).fetchone()[0]
        event, status = "posted", "new"
    conn.execute(f"INSERT INTO {PO} (observed_at, listing_id, property_id, source_key, listing_type, zip, beds, "
                 "price_usd, price_max_usd, trust_weight, event) VALUES (%s,%s,NULL,%s,'rent',%s,%s,%s,NULL,%s,%s) "
                 "ON CONFLICT (listing_id, observed_at, event) DO NOTHING",
                 (posted, lid, SOURCE, o["zip"], o["beds"], o["price_usd"], TRUST, event))
    return status


def load_offers(conn, offers: list[dict], target: str) -> dict:
    """Offers into `target`; for shared, only data/zips.txt ZIPs (others go to staging)."""
    core = core_zips()
    out = {"new": 0, "repost": 0, "seen": 0, "staged_outside_core": 0}
    for o in sorted(offers, key=lambda o: o["date_posted"]):
        t = target
        if target == "shared" and o["zip"] not in core:
            t = "staging"
            out["staged_outside_core"] += 1
        out[upsert_offer(conn, o, t)] += 1
    conn.commit()
    return out


def record_group(conn, g: dict, is_public: bool | None, last_post: datetime | None) -> None:
    conn.execute(
        "INSERT INTO fb_groups (url_hash, display_name, locality, zips, is_public, checked_on, last_post_date_seen) "
        "VALUES (%s,%s,%s,%s,%s,current_date,%s) ON CONFLICT (url_hash) DO UPDATE SET display_name = EXCLUDED.display_name, "
        "locality = EXCLUDED.locality, zips = EXCLUDED.zips, is_public = EXCLUDED.is_public, checked_on = current_date, "
        "last_post_date_seen = greatest(fb_groups.last_post_date_seen, EXCLUDED.last_post_date_seen)",
        (g["url_hash"], g["display_name"], g.get("locality") or "San Diego", g.get("zips") or [], is_public, last_post))


# ---------------------------------------------------------------- Bright Data
class CapExceeded(RuntimeError):
    pass


def run_snapshot(conn, groups: list[dict], limit: int, *, sample: bool, client=None, sleep=time.sleep,
                 max_wait: int = 3600) -> dict:
    """One trigger for every group. A snapshot reporting more records than groups x limit is cancelled."""
    template = load_template(SOURCE)
    limit = min(limit, bd.FB_MAX_PER_GROUP)
    inputs = [{"url": g["url"]} for g in groups]
    cap = len(inputs) * limit
    plan = bd.plan_run(conn, SOURCE, inputs, limit, note=("sample " if sample else "bulk ") + f"fb {len(inputs)} groups")
    client = client or bd.BrightDataClient()
    rid = plan["run_id"]
    conn.execute("UPDATE scrape_runs SET status = 'running' WHERE run_id = %s", (rid,))
    conn.commit()

    def fail(msg):
        conn.execute("UPDATE scrape_runs SET status = 'failed', finished_at = now(), "
                     "note = left(coalesce(note,'') || %s, 400) WHERE run_id = %s", (" | " + msg[:150], rid))
        conn.commit()

    try:
        snap = client.trigger(template["fetch"]["dataset_id"], inputs, limit, "collect")
        conn.execute("UPDATE scrape_runs SET snapshot_id = %s WHERE run_id = %s", (snap, rid))
        conn.commit()
        waited, i = 0, 0
        while True:
            info = client.progress_info(snap)
            n = info.get("records")
            if isinstance(n, int) and n > cap:
                client.cancel(snap)
                raise CapExceeded(f"snapshot {snap} reported {n} records over its cap {cap}; cancelled")
            st = info.get("status", "")
            if st == "ready":
                break
            if st in ("failed", "canceled") or waited > max_wait:
                raise RuntimeError(f"snapshot {snap} {st or 'timed out'}")
            d = bd.BACKOFF[min(i, len(bd.BACKOFF) - 1)]
            sleep(d)
            waited, i = waited + d, i + 1
        rows = client.snapshot(snap)
    except Exception as e:
        fail(str(e))
        raise
    records = len(rows)
    conn.execute("UPDATE scrape_runs SET status = 'ready', finished_at = now(), records = %s, est_usd = %s "
                 "WHERE run_id = %s", (records, bd.cost_of(records), rid))
    conn.commit()
    if records > cap:          # already delivered (and billed): stop before using any of it
        raise CapExceeded(f"snapshot {snap} delivered {records} records over its cap {cap}")
    return {"run_id": rid, "snapshot_id": snap, "rows": rows, "records": records, "usd": bd.cost_of(records), "cap": cap}


# ---------------------------------------------------------------- the step
def process(conn, raw_rows: list[dict], groups: list[dict], target: str, *, snapshot_id: str | None = None,
            parse=None, sleep=time.sleep, today: str | None = None) -> dict:
    """Snapshot rows -> fb_groups, raw_records (fields only), listings. Returns counts."""
    today = today or date.today().isoformat()
    posts_by, errors_by = split_by_group(raw_rows, groups)
    zips, hoods = sd_zips(), neighborhood_table()
    stats = {"groups_collected": [], "groups_skipped": [], "posts": 0, "usable": 0, "reasons": {}}
    offers, group_rows = [], []
    # Gemini first, with no database work in between (a long idle connection can time out); writes after.
    for g in groups:
        posts = posts_by.get(g["slug"], [])
        if not posts:
            err = (errors_by.get(g["slug"]) or ["returned nothing"])[0]
            private = bool(re.search(r"(?i)login|log in|private|permission|access", err))
            group_rows.append((g, False if private else None, None))
            stats["groups_skipped"].append({"name": g["display_name"], "reason": err})
            continue
        last = max((d for d in (parse_date(p.get("date_posted")) for p in posts) if d), default=None)
        group_rows.append((g, True, last))
        stats["groups_collected"].append({"name": g["display_name"], "posts": len(posts)})
        for p, fields in extract(posts, today, parse=parse, sleep=sleep):
            stats["posts"] += 1
            o, why = validate(p, fields, g, zips, hoods)
            stats["reasons"][why] = stats["reasons"].get(why, 0) + 1
            if o:
                offers.append(o)
    if callable(conn):          # a factory: open a fresh connection now that the slow part is done
        conn = conn()
    for g, pub, last in group_rows:
        record_group(conn, g, pub, last)
    conn.commit()
    stats["usable"] = len(offers)
    for o in offers:
        load.store_raw(conn, SOURCE, snapshot_id, content_hash(o), o)
    conn.commit()
    stats["usable_share"] = round(len(offers) / stats["posts"], 3) if stats["posts"] else 0.0
    stats["offers"] = offers
    stats["conn"] = conn
    return stats


def summarize(offers: list[dict]) -> dict:
    return {"whole_units": sum(o["unit_type"] == "entire_unit" for o in offers),
            "rooms": sum(o["unit_type"] == "room" for o in offers),
            "sublets": sum(o["unit_type"] == "sublet" for o in offers)}


def terms_checked(conn) -> bool:
    row = conn.execute("SELECT terms_checked_on FROM sources WHERE source_key = %s", (SOURCE,)).fetchone()
    return bool(row and row[0])


def replay(conn, target: str) -> dict:
    """Staged offers (raw_records) -> target tables; shared takes data/zips.txt ZIPs only."""
    rows = conn.execute("SELECT payload FROM raw_records WHERE source_key = %s ORDER BY id", (SOURCE,)).fetchall()
    offers = [p for (p,) in rows if isinstance(p, dict) and p.get("price_usd")]
    if target == "shared":
        core = core_zips()
        offers = [o for o in offers if o["zip"] in core]
    res = load_offers(conn, offers, target)
    return {"offers": len(offers), **res, **summarize(offers)}


def connect():
    """DATABASE_URL with TCP keepalives: Bright Data and Gemini waits leave the connection idle for minutes."""
    import os
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=False, keepalives=1, keepalives_idle=30,
                           keepalives_interval=10, keepalives_count=6)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "collect", "replay"])
    ap.add_argument("--limit", type=int, default=bd.FB_MAX_PER_GROUP, help="posts per group (max 50)")
    ap.add_argument("--target", choices=["staging", "shared"], default="staging")
    ap.add_argument("--confirm-shared", action="store_true")
    ap.add_argument("--cron", action="store_true", help="refuse unless sources.terms_checked_on is set")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--snapshot", help="reprocess a ready snapshot (download only; no new trigger, no new cost)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if a.target == "shared" and not a.confirm_shared:
        print("--target shared writes the live tables; add --confirm-shared", file=sys.stderr)
        return 2
    conn = connect()
    if a.cron and not terms_checked(conn):
        print(f"{SOURCE}: terms_checked_on is not set; refusing to run", file=sys.stderr)
        return 3
    if a.cmd == "replay":
        print(replay(conn, a.target))
        return 0
    groups = load_groups()
    if a.cmd == "sample":
        groups, limit = groups[:SAMPLE_GROUPS], SAMPLE_PER_GROUP
    else:
        limit = min(a.limit, bd.FB_MAX_PER_GROUP)
        if not bd.sample_done(conn, SOURCE):
            print(f"{SOURCE}: run `sample` first", file=sys.stderr)
            return 2
    est = bd.estimate(len(groups), limit)
    if a.dry_run:
        print({"groups": [g["display_name"] for g in groups], "limit": limit, "est_records": est[0], "est_usd": est[1]})
        return 0
    if a.snapshot:
        rows = bd.BrightDataClient().snapshot(a.snapshot)
        if len(rows) > len(groups) * limit:
            print(f"STOP: snapshot {a.snapshot} has {len(rows)} records over its cap", file=sys.stderr)
            return 4
        snap = {"snapshot_id": a.snapshot, "rows": rows, "records": len(rows), "usd": 0.0, "cap": len(groups) * limit}
    else:
        try:
            snap = run_snapshot(conn, groups, limit, sample=a.cmd == "sample")
        except CapExceeded as e:
            print(f"STOP: {e}", file=sys.stderr)
            return 4
    conn.close()
    stats = process(connect, snap["rows"], groups, a.target, snapshot_id=snap["snapshot_id"])
    offers, conn = stats.pop("offers"), stats.pop("conn")
    out = {"records": snap["records"], "usd": snap["usd"], "cap": snap["cap"], **stats, **summarize(offers)}
    if a.cmd == "sample" and stats["usable_share"] < MIN_USABLE_SHARE:
        print({**out, "STOP": f"usable share {stats['usable_share']} < {MIN_USABLE_SHARE}"})
        return 5
    out["load"] = load_offers(conn, offers, a.target)
    out["unusual"] = conn.execute(
        f"SELECT count(*) FROM {TABLES[a.target][0]} WHERE source_key = %s AND extras->>'unusual_price' = 'true'",
        (SOURCE,)).fetchone()[0]
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
