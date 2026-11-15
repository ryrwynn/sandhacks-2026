"""
Bright Data (Zillow, San Diego rentals) -> strip -> Django.

    export BRIGHTDATA_API_KEY=...
    export DJANGO_URL=http://localhost:8000/api/ingest/     # where the stripped rows get POSTed
    python scrapper/brightdata.py --dry-run                 # fetch + strip, print, don't send
    python scrapper/brightdata.py                           # fetch + strip + send

Standard library only.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request

BRIGHTDATA_URL = (
    "https://api.brightdata.com/datasets/v3/scrape"
    "?dataset_id=gd_lfqkr8wm13ixtbd8f5&notify=false&include_errors=true"
    "&type=discover_new&discover_by=input_filters"
)
SEARCH = [{"location": "San Diego", "listingCategory": "House for rent",
           "exact_address": False, "HomeType": "", "days_on_zillow": ""}]


def fetch(api_key: str) -> list[dict]:
    """The same request as the Node snippet. Returns the raw records Bright Data sends back."""
    body = json.dumps({"input": SEARCH, "limit_per_input": None}).encode()
    req = urllib.request.Request(
        BRIGHTDATA_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        text = resp.read().decode("utf-8").strip()

    # The response is either one JSON array or one JSON object per line.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    rows = data if isinstance(data, list) else [data]

    # Big jobs don't finish inside the synchronous window; Bright Data answers with a snapshot id instead.
    if rows and "snapshot_id" in rows[0] and "zpid" not in rows[0]:
        raise RuntimeError(
            f"Result too large to return inline (snapshot {rows[0]['snapshot_id']}). "
            "Poll /datasets/v3/progress/<id>, then download /datasets/v3/snapshot/<id>?format=json."
        )
    return rows


def strip(raw: dict) -> dict | None:
    """Keep only what the database needs. Error records and rows without an id are dropped."""
    if raw.get("error") or not raw.get("zpid"):
        return None
    addr = raw.get("address") or {}
    return {
        "zpid": str(raw["zpid"]),
        "url": raw.get("hdpUrl") or raw.get("url"),
        "street": addr.get("streetAddress") or raw.get("streetAddress"),
        "unit": raw.get("unit_number"),
        "city": addr.get("city") or raw.get("city"),
        "state": addr.get("state") or raw.get("state"),
        "zipcode": addr.get("zipcode") or raw.get("zipcode"),
        "bedrooms": raw.get("bedrooms"),
        "bathrooms": raw.get("bathrooms"),
        "sqft": raw.get("livingArea") or raw.get("sqft"),
        "home_type": raw.get("homeType"),
        "status": raw.get("homeStatus"),
        "rent": raw.get("price"),
        "latitude": raw.get("latitude"),
        "longitude": raw.get("longitude"),
        "days_on_zillow": raw.get("daysOnZillow"),
    }


def send_to_django(rows: list[dict], url: str, token: str = "") -> str:
    payload = {"source": "zillow", "scraped_at": dt.date.today().isoformat(), "listings": rows}
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="fetch and strip, but don't send to Django")
    args = ap.parse_args()

    api_key = os.environ.get("BRIGHTDATA_API_KEY")
    if not api_key:
        sys.exit("Set BRIGHTDATA_API_KEY.")

    raw = fetch(api_key)
    rows = [r for r in (strip(x) for x in raw) if r]
    print(f"{len(raw)} records from Bright Data, {len(rows)} kept after stripping.")

    if args.dry_run:
        print(json.dumps(rows[:2], indent=2))
        return

    url = os.environ.get("DJANGO_URL")
    if not url:
        sys.exit("Set DJANGO_URL (or use --dry-run).")
    print("Django replied:", send_to_django(rows, url, os.environ.get("DJANGO_TOKEN", "")))


if __name__ == "__main__":
    main()
