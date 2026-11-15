"""
Refresh just the PRICE of listings we already know, then send it to Django's prices endpoint.

    python scrapper/price_refresh.py --zpid 67712440 69188022 --dry-run
    python scrapper/price_refresh.py --file zpids.txt --limit 50          # one zpid or Zillow URL per line
    python scrapper/price_refresh.py --snapshot sd_xxxx --dry-run         # resume a refresh job

Input items can be a zpid, a /homedetails/..._zpid/ URL, or an apartments URL ending in #unit-<zpid>.
Uses the same Bright Data dataset as discovery, "collect by URL" mode: one record (= one credit) per URL.

A returned record is only accepted if its zpid is one we asked for. Anything else is counted and
ignored, so a wrong match can never write a price onto the wrong listing.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

from brightdata import COLLECT_URL, post_json, run_job

CONFIRM_ABOVE = 100  # ask before spending credits on more URLs than this


def zpid_of(item: str) -> str | None:
    m = re.search(r"#unit-(\d+)", item) or re.search(r"(\d+)_zpid", item) or re.fullmatch(r"\s*(\d+)\s*", item)
    return m.group(1) if m else None


def to_url(item: str) -> str:
    item = item.strip()
    return item if item.startswith("http") else f"https://www.zillow.com/homedetails/{item}_zpid/"


def price_row(raw: dict, observed_on: str) -> dict:
    """Current price + status for one refreshed listing. Price only counts while it is still for rent."""
    status, price = raw.get("homeStatus"), raw.get("price")
    live = status == "FOR_RENT" and isinstance(price, (int, float)) and price > 0
    return {"zpid": str(raw["zpid"]), "observed_at": observed_on, "price": int(round(price)) if live else None, "status": status}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zpid", nargs="+", default=[], help="zpids or Zillow URLs")
    ap.add_argument("--file", help="text file, one zpid or URL per line (# comments allowed)")
    ap.add_argument("--limit", type=int, help="refresh at most this many listings")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help=f"skip the confirmation prompt above {CONFIRM_ABOVE} listings")
    ap.add_argument("--snapshot", help="resume an existing refresh job")
    ap.add_argument("--timeout", type=int, default=1200)
    args = ap.parse_args()

    api_key = os.environ.get("BRIGHTDATA_API_KEY")
    if not api_key:
        sys.exit("Set BRIGHTDATA_API_KEY in .env")

    items = list(args.zpid)
    if args.file:
        items += [l.strip() for l in open(args.file, encoding="utf-8") if l.strip() and not l.startswith("#")]

    requested: dict[str, str] | None = {}
    unparseable = 0
    for it in items:
        z = zpid_of(it)
        if z:
            requested.setdefault(z, to_url(it))
        else:
            unparseable += 1
    if args.limit:
        requested = dict(list(requested.items())[: args.limit])
    if not requested:
        if not args.snapshot:
            sys.exit("Nothing to refresh. Pass --zpid or --file.")
        requested = None                       # resuming a job with no list: accept every returned record

    if requested is not None:
        print(f"{len(requested)} listings to refresh (about {len(requested)} credits at 1 credit per record)" +
              (f"; {unparseable} inputs had no zpid and were skipped" if unparseable else ""))
        if len(requested) > CONFIRM_ABOVE and not args.yes and not args.dry_run:
            if input("Continue? [y/N] ").strip().lower() != "y":
                return

    raw = run_job(api_key, COLLECT_URL, [{"url": u} for u in (requested or {}).values()],
                  timeout_s=args.timeout, snapshot_id=args.snapshot)
    if raw is None:
        return

    today = dt.date.today().isoformat()
    rows, got, errors, unrequested = [], set(), 0, 0
    for r in raw:
        if r.get("error") or not r.get("zpid"):
            errors += 1
        elif requested is not None and str(r["zpid"]) not in requested:
            unrequested += 1
        else:
            got.add(str(r["zpid"]))
            rows.append(price_row(r, today))
    not_returned = sorted(set(requested) - got) if requested else []
    print(f"{len(raw)} records back -> {len(rows)} price rows | {errors} errors | {unrequested} ignored (zpid not requested) | {len(not_returned)} requested but not returned")

    if args.dry_run:
        print(json.dumps({"prices": rows[:3], "not_returned": not_returned[:5]}, indent=2))
        return

    url = os.environ.get("DJANGO_PRICES_URL")
    if not url:
        sys.exit("Set DJANGO_PRICES_URL in .env (or use --dry-run).")
    payload = {"source": "zillow", "scraped_at": today, "prices": rows, "not_returned": not_returned}
    print("prices ->", post_json(url, payload, os.environ.get("DJANGO_TOKEN", "")))


if __name__ == "__main__":
    main()
