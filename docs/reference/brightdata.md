# Bright Data: reference for RentOrKnot

Sources: `docs/reference/raw/brightdata/public-docs-notes.md` and `account.txt` (paraphrased, read 2026-11-15), plus a check of docs.brightdata.com. Items marked UNVERIFIED were not confirmed on a page.

## Budget rules (from NIGHT.md)
- Spend at most `BRIGHTDATA_BUDGET_USD` tonight (default **10** if unset). Estimate cost from record counts before every trigger, and refuse if it would cross the budget.
- Sample first: a **20-record** run of every new input type before any bulk run.
- Record each run's records and estimated cost in `scrape_runs` (migration 002).
- Batch many inputs into one trigger. Cap records per input with `limit_per_input`. Poll with backoff. Don't re-trigger.
- Free credits left (dashboard, 2026-11-15 00:48 PT): **3,108 of 5,000** this month. Renewal Dec 1, 2026. Roughly 1 credit = 1 record, so about **3,100 records** are free tonight.
- The $100 hackathon credit is not on the free-credits panel. Check Billing before counting on it.

## Prices and limits
| Item | Value |
| --- | --- |
| Scraper API, pay as you go | **$1.50 per 1,000 successful records** |
| Bad inputs | Still billed |
| Free tier | 5,000 credits a month, shared across products; unfunded accounts stop hard at zero |
| Example | 20,000 records is about $30 |
| Zillow dataset marketplace | From $0.0025 per record, **$250 minimum order**. Out of budget tonight. |
| Dataset filter API (`/datasets/filter`) | $2.50 per 1,000 records returned |
| SERP API price | UNVERIFIED (see Missing) |

Other limits:
- Up to **1 GB** of input per job; **5,000** active jobs per account.
- Snapshots stay downloadable for **30 days**. Copy them within that window.
- Download request limit: **5 GB** per request.
- Webhooks must return 200 within **30 s**, or they are retried.
- Rate limiting: 25 or more 429s from one IP in 5 minutes blocks that IP for an hour. Honor `Retry-After`; otherwise back off 2, 4, 8, 16, 32 s with jitter.

## Scraper API flow
Base URL: `https://api.brightdata.com/datasets/v3`
Header: `Authorization: Bearer <BRIGHTDATA_API_TOKEN>` (read the token from the environment; never log it).

1. `POST /trigger?dataset_id=<id>&...` returns `{"snapshot_id": "sd_..."}`.
2. `GET /progress/{snapshot_id}` until `status` is `ready`. Statuses: `starting`, `running`, `ready`, `failed`, `canceled`. A `failed` job carries `error_message` (for example "Snapshot is empty").
3. `GET /snapshot/{snapshot_id}?format=ndjson&compress=true` to download.
   - `200`: data.
   - `202` or `409`: not ready; retry after about 10 s.
   - `400`: expired or empty. `404`: unknown snapshot.
   - For large snapshots, use `batch_size` (minimum 1000) with `part`. The part count comes from `GET /snapshot/{id}/parts`.
4. `POST /scrape` is synchronous (waits up to 1 minute) and is for a single input only. Use `/trigger` for batches.

### Trigger parameters
- Query: `dataset_id` (required), `include_errors=true`, `type=discover_new` (discovery inputs only), `discover_by=url` (search URL), `limit_per_input`, `limit_multiple_results` (OpenAPI spec only), `notify=false` (the docs disagree on its type; send the boolean `false`), `endpoint` (webhook URL), `auth_header`, `uncompressed_webhook`, `format` (`json`, `ndjson` default, `jsonl`, `csv`), `deadline`.
- Body:
  ```json
  {"input": [{"url": "https://www.zillow.com/..."}], "limit_per_input": 50}
  ```
  A bare array works, but then `limit_per_input` can only go in the query string.

### Other endpoints
- `GET /snapshots?dataset_id=&status=ready&limit=` (max 5000; also `from_date`, `to_date`, `with_total`)
- `POST /snapshot/{id}/cancel`, `POST /snapshot/{id}/rerun`
- `GET /snapshot/{id}/input`
- `POST /deliver/{id}`, then `GET /delivery/{delivery_id}`

### Sample trigger (Python, 20-record sample)
```python
import os, requests
H = {"Authorization": f"Bearer {os.environ['BRIGHTDATA_API_TOKEN']}"}
params = {"dataset_id": os.environ["BD_ZILLOW_LISTINGS_ID"], "include_errors": "true",
          "notify": "false", "format": "ndjson"}
body = {"input": [{"url": u} for u in urls[:20]], "limit_per_input": 20}
r = requests.post("https://api.brightdata.com/datasets/v3/trigger",
                  headers=H, params=params, json=body, timeout=30)
snapshot_id = r.json()["snapshot_id"]
```
Use env var names from `.env`. Do not hard-code dataset IDs in the app if they can vary; keep them in `sources/*.yaml`.

## Zillow (Scraper API)
| Dataset ID | Name | Notes |
| --- | --- | --- |
| `gd_lfqkr8wm13ixtbd8f5` | Properties listing information | About 139 fields. Methods: `collect_by_url`, `discover_by_url` (search URL), `discover_by_input_filters` (location, home type, status; exact field names UNVERIFIED). |
| `gd_lxu1cz9r88uiqsosl` | Price history | One row per event (date, event, price, rate, source, rental flag). Not needed: the listing record already has `priceHistory`. |
| `gd_m71oxpvxwr113ehqg` | Search-page scraper | One row per search result, 26 fields, faster. |
| `gd_m794g571225l6vm7gh` | Full property information | Collect by URL, or discover by search URL. |

Key listing fields: `zpid`, `address{}`, `city`, `state`, `homeStatus`, `bedrooms`, `bathrooms`, `price`, `yearBuilt`, `zestimate`, `priceHistory[]`, `taxHistory[]`, `timestamp`.

Cheapest discovery: billing is per delivered record, so filter at the source. Use one rental-only search URL per ZIP with `discover_by=url`. The Bright Data blog reported about 1,295 listings from one search URL in 13 to 17 minutes. Rental status values (for example `FOR_RENT`) are UNVERIFIED.

## Facebook posts by group
- Dataset ID: `gd_lz11l67o2cb3r0lkj3`. Method: `collect_by_url` only.
- Input: `{"url": "https://www.facebook.com/groups/<id>"}`
- **No post-count or date-range input is documented.** Cap each run with `limit_per_input` (at most 50 per NIGHT.md), test that the cap works on a sample, and filter on `date_posted` after download.
- Output fields: `url`, `post_id`, `user_url`, `user_username_raw`, `content`, `date_posted`, `num_comments`, `num_shares`, `group_name`, `group_id`, `group_url`, `group_category`, `group_logo`, `group_members`, `group_created_at`, `user_is_verified`, `attachments`, `post_type`, `likes`, `profile_id`.
- **Personal fields to drop before storage:** `user_url`, `user_username_raw`, `profile_id`, `user_is_verified`. `content` and `attachments` can also hold personal details. Hash `post_id`, redact text, and never show post text (per NIGHT.md).
- Group discovery by locality: not documented. Options are web search, or the SERP API if a SERP zone exists (see Missing).

## Dataset marketplace and filter API
- `POST https://api.brightdata.com/datasets/filter` with `{dataset_id, records_limit, filter}`; returns a `snapshot_id`.
- Filter: `{"name": ..., "operator": ..., "value": ...}`, or `{"operator": "and"|"or", "filters": [...]}`. Nesting depth max 3.
- Limits: 5-minute job timeout; 5 requests per minute and 120 per hour; 25 parallel jobs per dataset.
- Status codes: `402` not enough funds; `422` zero matches (free).
- Zillow can be bought filtered by state, city or ZIP per the product page, but the marketplace dataset ID and field names were not found.
- **Out of budget tonight** ($250 minimum). Do not use it for NIGHT.md's default plan.

## Cost tips
- Sample with `limit_per_input` of 20 to 50 first.
- Use rental-only search URLs and one trigger per run.
- Dedupe on `zpid` and `post_id`. Keep a high-water mark per Facebook group (`date_posted`).
- Use `include_errors=true` and retry only the failed inputs.
- Use `ndjson` with `compress=true`.
- Validate inputs before triggering.
- Copy snapshots within 30 days.

## Missing
- **Zillow `discover_by_input_filters` input names** and its `discover_by` value. Fallback: use `discover_by=url` with a rental-only search URL per ZIP.
- **Rental status value names** (for example `FOR_RENT`). Fallback: filter on `homeStatus` after download and record the values seen in `scrape_runs`.
- **Facebook group inputs beyond `url`.** Fallback: `limit_per_input` (<= 50) plus `date_posted` filtering after download.
- **Facebook group discovery by location.** Fallback: web search for public group URLs per locality, recorded in `fb_groups`; or SERP API if a zone exists.
- **SERP API price and zone setup.** Fallback: treat SERP as unavailable and budget 0 for it; use web search instead.
- **Zillow marketplace dataset ID** and its fields. Fallback: none tonight, since the $250 minimum is over budget. Use the scraper listing dataset above.
- **Account zones and dataset IDs** (`account.txt` says "not copied yet"). Fallback: dataset IDs above from public docs; confirm in the dashboard before the first bulk run.
- **Per-scraper prices beyond the general $1.50 per 1,000 rate.** Fallback: assume $1.50 per 1,000 records and check the first 20-record sample's billed amount.
- **`notify` parameter type conflict.** Fallback: send the boolean `false`; if the API returns 400, try the string `"false"` once and report.
- **Public trigger endpoint page.** A direct docs URL guess returned 404; the endpoint details above come from the raw notes. Fallback: verify against the 20-record sample.
