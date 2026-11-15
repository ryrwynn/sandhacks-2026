# Final run (2026-11-15, ends 11:25 AM PST): ready to merge

Branch `night`, PR #2 marked ready for review (not merged). Nothing pushed to Setup or main; no deploy, no change to
deploy.yml, secrets or the server. Local servers stopped. Facebook rows are in staging only (not replayed to shared).

## Results

| Step | Result |
| --- | --- |
| 1. Database | Reachable (8 s timeout). |
| 2. Schedules and rules | `zillow_rent` weekly, Thursday 12:00 UTC (4:00 AM PST, 5:00 AM during daylight time); `zillow_sale` and train unchanged. The active window (latest scrape per source minus 36 h) and Price alerts work with a weekly scrape; UI says "Updated weekly". `FMR_RULE_VERIFIED = True`. **HUD's SAFMR file was refused again** (HTTP 202, empty body), so `fmr.yaml` stays unverified and the 160% path still answers "unclear". |
| 3. Facebook | Prompt fixed: rooms offered in a shared home are offers (`unit_type` room, `roommate_wanted`); people looking for a place stay out. Full run re-extracted with no new scrape (~30 Flash Lite calls). See the counts below. |
| 4. 12-ZIP guard | Every live market, listing, median, comparable and `zip_features` query in `api/db.py` filters to `data/zips.txt`; 24 tests in `api/tests/test_zip_filter.py`. |
| 5. Partner fixes | a: /buyer values at most 2 decimals, ratios as % (yield, % of budget). b: "Find a place" tab removed; Starter finder is a "Not sure where to look?" panel on /find whose "Show listings in {area}" sets the area filter. c: Save button pinned to the card bottom, cards equal height. d: logo favicon (`app/icon.svg`, `apple-icon.png`), `favicon.ico` removed. e: `ListingSummary.tags` (≤ 4; Zillow washer/dryer, dishwasher, hardwood; Facebook amenities; area tags "(ZIP)" for the top third per km²) and `roommate_wanted` (contract change, fixtures, types). f: /saved multi-select (shift / Ctrl / Cmd-click, Select mode with checkboxes, action bar with open-in-tabs plus a blocked-links list, remove with undo, Escape). g: "Roommate wanted" / "Sublet" tags; unit filter "Roommate wanted (rooms)". |
| 6. Privacy and terms | /privacy and /terms (Last updated November 15, 2026), linked from a new footer, /about and the sign-in button. Privacy also says that rent increase checks are stored. **A lawyer has not reviewed either page.** |
| 7. Docs | PLAN "Current state", DESIGN (Find, cards, Saved, sign-in, footer), ACCOUNTS step 2 (`{"enabled": false}`). |
| 8. Checks | See below. |

### Facebook (full run `sd_mwhxcv0l15owbti9eg`, re-extracted)

6 public groups (UCSD group private, skipped), **290 posts, 133 usable (45.9%)**: **18 whole units, 94 rooms (all 94
roommate-wanted), 21 sublets, 0 unusual prices**. Dropped: 70 not offers (people looking, services), 47 no ZIP, 40 no
price or beds. After dedupe and reposts, staging holds **107 listings** (13 whole, 78 rooms, 16 sublets), **52 in
the 12 ZIPs** (those are what `replay --target shared` will load), and 134 price observations. The sample wasn't
re-extracted on its own: all 40 of its posts are in the full run.

## Checks

- `./scripts/preflight.sh`: all OK except **FAIL "on battery"** (this laptop's power) and WARNs (no DEV_DATABASE_URL,
  extra non-app tables, no local Docker). Nothing it checks was changed.
- `uv run pytest api/tests -q`: **299 passed** (new: roommate extraction 3, ZIP filter 24, area/listing tags 2,
  FMR verified 2).
- `npm run build` and `npx tsc --noEmit`: pass.
- `node scripts/ui-check.mjs` (API with `RENTORKNOT_READ_STAGING=1`, production build): **186/186**. That covers 22
  pages (now with /privacy, /terms and a Facebook room) × 2 widths × 4 themes, plus the new checks: a pan from San Diego
  that loads the Orange County shapes at 375px, first paint in each theme with no flash, a first visit with
  prefers-color-scheme dark getting Cocoa Night, two shift-clicks on /saved showing the action bar (Escape clears it),
  and the Find Starter panel. Earlier runs failed only on headless Chromium running out of software WebGL contexts;
  the script now starts a fresh browser every batch. Use `UI_BATCH=6 UI_PARALLEL=2` for a clean run.
- Screenshots reviewed: Find (tags, aligned Save buttons, Starter panel), Find filtered to Facebook, a Facebook room,
  /saved with a selection, /buyer, /gouging, /privacy, the map pan. Fixed from that review: the sign-in note overflowed
  the 375px header (now a compact "Privacy" link, and "Sign in" doesn't wrap); the Starter default budget ($2,200)
  matched no ZIP (now $3,000); lowercase neighborhood names in Facebook titles are title-cased.
- Capacity SQL (read-only parts): database 126 MB; hot queries 17 ms and 3 ms (docs/TIGER_CAPACITY.md).
- Google sign-in (keys loaded): `/auth/session` is `null` when signed out (no email or name), the provider list is
  Google only, the button shows, `/auth/saves` answers 401 without a session, and a wrong `ACCOUNT_API_TOKEN` gets a
  401 that the button ignores (local saves untouched). The real sign-in is left to you.

## Costs

- Gemini today in this run: ~30 Flash Lite requests (Facebook re-extract) plus a few cached ranking summaries.
- Bright Data in this run: $0 (no scrape; snapshots were only downloaded).

## Bright Data cost after the merge (from Bright Data's snapshot list, `dataset_size`)
 (from Bright Data's snapshot list, `dataset_size`)

Zillow dataset `gd_lfqkr8wm13ixtbd8f5` snapshots today (UTC): `zillow_rent` 06:00 **486**, 09:00 **759**, 12:00
**1,777**, 15:00 **1,777**, 18:00 **348**; `zillow_sale` 04:30 **240**; county sample 14:11 96. At $1.50 per 1,000 records:

| Job | Schedule | Records a month | USD a month |
| --- | --- | --- | --- |
| `zillow_rent` | weekly, Thu 12:00 UTC | 4.35 runs × 348–1,777 ≈ 1,500–7,700 | **$2.30–$11.60** (plan for the high end) |
| `zillow_sale` | daily 04:30 UTC (unchanged) | 30 × 240 ≈ 7,200 | ≈ $10.80 |
| Facebook groups | Mon + Thu 15:00 UTC | ≈ 2,600 | ≈ $3.90 |
| **Total** | | ≈ 11,000–17,500 | **≈ $17–$26** (was ≈ $650) |

Until the merge deploys, the server still runs `zillow_rent` every 3 hours (each run up to ≈ $2.70).


## Not done

- HUD FY2026 Small Area FMRs: huduser.gov refuses automated downloads. Download the file by hand into
  `api/rules/data/` and set `verified: true` with the source to give firm 160% answers.
- Step 3 of the capacity study (scratch schema) was skipped because it writes to the shared database.
- The privacy and terms pages haven't had a legal review.

## Ready-to-merge checklist (for "go")

1. Say **go**: merge PR #2 into Setup; follow the deploy with `./scripts/watch-deploy.sh $(git rev-parse origin/Setup)`.
2. After the smoke test passes: `uv run python -m worker.facebook replay --target shared --confirm-shared` (52 listings
   in the 12 ZIPs).
3. `./scripts/smoke.sh https://rentorknot.us` and `node scripts/ui-check.mjs https://rentorknot.us`.
4. Then sign in with Google once on the live site (docs/ACCOUNTS.md steps 3–7) and add
   `https://rentorknot.us/privacy` and `https://rentorknot.us/terms` to the Google consent screen.
5. The server keeps running `zillow_rent` every 3 hours until the merge deploys the weekly crontab.

# Wake-up report: morning run, 2026-11-15 (earlier)

Branch `night` (draft PR #2 → Setup). Nothing pushed to Setup or main, PR #2 not merged, no deploy, no change to
deploy.yml, secrets or the server. Local servers stopped.

## Read first

1. **The live Zillow job costs far more than planned: about $640 a month.** Bright Data's snapshot list shows the
   3-hourly `zillow_rent` run delivered **1,777 records** at 12:00 and 15:00 UTC today (06:00: 486, 09:00: 759), for a
   nominal cap of 120 (12 ZIPs × `limit_per_input` 10). `limit_per_input` is not a hard cap: buildings expand into one
   record per unit (my county sample confirmed it: cap 18, delivered 96). 1,777 × 8 runs × 30 days ≈ 426,000 records ≈
   **$640/month** at $1.50 per 1,000; the free records left this month (3,108 per MORNING.md) are gone after two runs.
   `zillow_sale` (≈240/day) adds ≈ $11/month. I changed nothing on the server. Options: run `zillow_rent` once or twice a
   day (≈ $80 or $160/month), cut it to the ZIPs that change, or cap by dropping inputs after the first N records.
2. **This laptop lost its connection to the Tiger database around 07:00** (TCP to the database port times out; DNS and
   the internet are fine, and the live site still reads the database: https://rentorknot.us/api/health was ok). The full
   Facebook collection was scraped and paid for but not written; resume it for free with
   `uv run python -m worker.facebook collect --snapshot sd_mwhxcv0l15owbti9eg` (Gemini answers are cached). Everything
   after 07:00 that needs the database (preflight, the final UI-check run, the ZHVI retrain option) is marked below.
3. **`sources.facebook_groups_sd.terms_checked_on` is already set (2026-11-15).** You said you'd set it; I didn't, and I
   left it alone. With it set, the new Monday/Thursday cron will run after the merge deploys. Clear it if you haven't
   read the terms: `UPDATE sources SET terms_checked_on = NULL WHERE source_key = 'facebook_groups_sd';`
4. Server: 1 GB of RAM, and its `.env` predates the night keys (`BRIGHTDATA_BUDGET_USD`, `ONDEMAND_DAILY_USD`,
   `LLM_EXTRACT_MAX_PER_RUN`, Google/AUTH keys). Without `BRIGHTDATA_BUDGET_USD` the budget guard defaults to $10 per
   24 hours, which the Facebook cron fits; the live `zillow_rent` job doesn't go through that guard.

## Done

| Step | Result |
| --- | --- |
| 1. Data | "Load the data" 1–3 marked done (not rerun). raw_records: `zillow_research_ca` 2,493, `census_acs_ca` 3,056. County CLI `worker/county.py` (sample/bulk, refuses core ZIPs, staging only). Sample 92037/92014/92106: 96 records, $0.144, 96 staged. Zillow fields confirmed: input `{"url"}` with `discover_by=url`; output `zpid`, `price`, `bedrooms`, `bathrooms`, `homeStatus=FOR_RENT`, `streetAddress`, `zipcode`. |
| 2. Local stack | `uv sync`, API :8000, `npm ci` + production build :3000. pytest, tsc, build all pass (tsc needs a build first: Next generates `PageProps`). |
| 3. Facebook | Collector, Gemini extraction, staging listings with repost history, API, UI, cron, tests (details below). |
| 4. Browser check | `scripts/ui-check.mjs` (Playwright in `scripts/package.json`, outside both images). |
| 5. Fixes | Listed below. |
| 6. Readiness | Preflight: see "Preflight". Cost estimate above. |

### Facebook groups

| Group | Result |
| --- | --- |
| San Diego Housing, Rooms, Apartments, Sublets | public, 50 posts |
| San Diego Apartments & Housing (NO SPAM) | public, 50 posts |
| San Diego Housing, Rooms, Apartments, Sublets, Roomster | public, 41 posts (9 empty) |
| San Diego Housing, Rooms, Apartments, Sublets (Neighborly Group) | public, 49 posts (1 empty) |
| San Diego Sublets | public, 50 posts |
| San Diego Roommates | public, 50 posts |
| UCSD Student Off-Campus Housing | **skipped: private group** (removed from /about) |

- Sample (2 groups × 20): 40 records = cap, $0.06. 23 of 40 usable (57.5%; gate 25%): **4 whole units, 18 rooms,
  1 sublet, 0 unusual prices**. Drop reasons: 9 no price or beds, 5 no ZIP, 3 not an offer. These 23 are staged
  (`staging_listings`, `staging_price_observations`) and `fb_groups` has the two groups.
- Full run: snapshot `sd_mwhxcv0l15owbti9eg`, 301 records (cap 350), ≈ $0.45. Gemini parsed it; the database write
  failed on the connection loss above, so its listings aren't stored yet (resume command above). Expect roughly the
  sample's mix: mostly rooms.
- Bright Data spend today: $0.144 (county) + $0.06 (FB sample) + ≈ $0.45 (FB full) ≈ **$0.65** of the $10 budget.
  Gemini: about 40 Flash Lite requests.

How it works: `worker/facebook.py` reads only post id, post URL, text, date and group fields (author fields, names,
profile links, photos are never read). Text is redacted, sent to Gemini 10 posts per request, each answer validated
alone, and never stored. A post becomes a listing when it is a rental offer with price, beds and a San Diego ZIP (ZIP
written in the post, else the reviewed `data/fb_neighborhood_zips.csv`, 77 single-ZIP names; multi-ZIP cities like
Carlsbad are dropped). Listing: `facebook_groups_sd`, property_id null, precision `zip`, trust 0.5, extras = unit type,
amenities, group name, canonical post URL, available date. Same normalized text + beds + ZIP within 30 days is one
listing; reposts are `posted`/`price_change` observations; inactive 21 days after the last post. Shared target takes
`data/zips.txt` ZIPs only.

API: listing fields `source_kind`, `source_label`, `unit_type`, `location_precision`, `post_url`, `group_name`,
`posted_at`, `available_date`, `amenities`, `unusual_price`, `trust_weight`; filters `source=all|listing_sites|facebook`
and `unit_type`; weighted medians (Facebook whole units at 0.5; rooms, sublets and unusual prices never); market and
ZIP responses carry a source breakdown and accept `listing_sites_only=true`; `/health` has per-source counts; rooms get
no fair-rent label; `RENTORKNOT_READ_STAGING=1` (local only) adds staged Facebook rows. Migration 003 (additive,
applied): `staging_price_observations` and dedupe indexes.

Freshness: `docker/worker.crontab` runs `worker.facebook collect --limit 50 --target shared --cron` Mondays and
Thursdays 15:00 UTC; `--cron` refuses unless `terms_checked_on` is set. **Monthly cost ≈ $3.90** (6 groups × 50 × 2 a
week ≈ 2,600 records), ≈ 70 Gemini Flash Lite requests a month.

### Fixes (step 5)

- `/find?source=facebook` showed listing-site rows: a stale default request finished last. Only the latest request
  updates the list now.
- "House" filter sent `single_family`, which the API rejects (422). Sends `house` now.
- `/auth/session` answered 404 on every page while sign-in is off (a console error everywhere); now 200 `{"enabled": false}`.
- `/listings/{id}/trends` 500 for listings in ZIPs without ZORI (pandas on an empty series).
- Buyer "why this ZIP" text quoted raw ratios ("0.9097725641018704"); Gemini now gets only the reason labels.
- Map legend covered the Mapbox logo; legend title used a fixed slate color (unreadable on dark themes).
- `/apartments/{id}` has an `<h1>` while loading and on error (it was client-only).
- ZHVI: cone not widened (needs a retrain against the database). The ZIP charts now print the measured held-out
  coverage from the latest training, with "the target is 80%, so treat it as a little narrow" below 80%. MODEL_CARD.md
  updated.
- Penal Code 396: `GougingResponse.unverified` lists unchecked inputs (the 160% FMR rule, FMR figures, unverified
  declarations); any of them turns a firm verdict into "unclear", and the page shows an "Unverified" note.
  Flip `FMR_RULE_VERIFIED` in `api/rules/gouging.py` after reading the statute.

## Tests and checks

- `uv run pytest api/tests -q`: **268 passed** (247 + 18 Facebook + 1 trends + 2 gouging).
- `tsc` clean, `npm run build` passes.
- UI check (152 loads: 19 pages × 375/1280 × 4 themes) against localhost with the database up: run 1 0/152 (the
  `/auth/session` 404 on every page), run 2 **133/152**; all 19 failures were Chromium running out of software-WebGL
  contexts in the last two themes (the script now starts a browser per theme). No horizontal scroll at 375px and every
  page had an h1. Screenshots reviewed: every page in Desert Clay at both widths, home/Find/ZIP in the others; the
  defects above came from that review. The final rerun after the fixes couldn't run because the database dropped.
- Not loaded on purpose: `/renter/letter/[id]` (opening it asks Gemini for a letter).

## Preflight

**Not completed.** `./scripts/preflight.sh` printed nothing for 10 minutes and was stopped: it hangs on the database
check while this laptop can't reach the database. The run at the start of the night was all clear (WARN: no
DEV_DATABASE_URL, no Google keys, no local Docker). Rerun it when the connection is back. I changed nothing it checks.

## Couldn't do

- Write the full Facebook run's listings (database unreachable; resume command above), and so the final whole-unit /
  room / unusual counts for it.
- Final UI-check rerun after the fixes (needs the database for real pages).
- Widen the ZHVI cone (needs a retrain).

## Needs you

1. Decide the `zillow_rent` frequency before the free records run out (Read first, 1).
2. `terms_checked_on` for `facebook_groups_sd` (Read first, 3).
3. Database access from this laptop; then run the resume command and `node scripts/ui-check.mjs`.
4. Add the night keys to the server's `.env` before the merge (Read first, 4).
5. Then "go" for the merge steps a–e in the morning prompt.
