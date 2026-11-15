# Decisions and known issues

Newest at the bottom of each section. The orchestrator writes here; lanes report to the orchestrator.

## Phase 0: preflight (2026-11-14)

`./scripts/preflight.sh`: 6 FAILs, all deploy-side; the Vultr server isn't set up yet.

| Check | Result | What happens instead |
| --- | --- | --- |
| VULTR_HOST | empty | Deploy steps skipped; the stack is tested locally (uvicorn + `npm start`) |
| Deploy key `~/.ssh/rentwatch_deploy` | missing | Same |
| Domain rentorknot.us | resolves to the registrar's parking IP, not the server | Same; add the A record once the server exists |
| GitHub secrets VULTR_HOST, VULTR_SSH_KEY, PUBLIC_URL | missing | The deploy workflow is disabled (`gh workflow enable deploy` when ready) |

Everything else passed: Tiger Cloud connects with timescaledb_toolkit 1.26.0; PARSE_MODEL and LETTER_MODEL
are both gemini-3.1-flash-lite (200) and the fallback gemini-3.5-flash-lite (200); the Bright Data token,
Census key and Mapbox public token are valid. No local Docker, so `docker compose` is only checked for syntax here.

## Phase 1: M1

- **llm_cache table** (in 001_init.sql): caches every Gemini answer that passed validation, keyed by
  sha256(job + prompt + schema), so repeat page loads, tests and smoke runs spend none of the free-tier
  quota (about 500 requests a day on Flash Lite).
- **001_init.sql is re-runnable** (IF NOT EXISTS everywhere, `if_not_exists => true` on hypertables and
  the aggregate policy), and the continuous aggregate is created `WITH NO DATA` so it applies on an empty
  database. `scripts/migrate.sh` applies the migration and both seeds; applied to Tiger on 2026-11-14.
- **The 12 ZIP codes** (the plan doesn't list them), in `data/zips.txt`: 91910 Chula Vista, 92101 Downtown,
  92103 Hillcrest, 92104 North Park, 92105 City Heights (the demo renter), 92107 Ocean Beach, 92108 Mission
  Valley, 92109 Pacific Beach, 92111 Linda Vista, 92117 Clairemont, 92122 University City, 92126 Mira Mesa.
- **Money in the API is JSON numbers**, not Decimal strings: the rules engine works in Decimal and the router
  converts, so `max_legal_rent` is `2272.2` in JSON and the web client gets plain numbers.
- **The letter has placeholders** (`[Tenant name]`, `[Landlord name]`) instead of taking names, so no names
  reach Gemini or the cache, and one cached letter serves every tenant with the same numbers. The page fills
  the names in on the user's screen.
- **CanonicalListing gained `price_history`** (list of {date, price_usd, event}) so the loader can write the
  source's own history as `price_observations` with event='history'. Nothing is ever invented.
- **CheckResult gained optional fields** (`overage_yearly`, `increase_pct`, `third_increase`, `figures`) that
  the API response needs; the plan's five fields are unchanged.
- **Gemini stubs return None** until lane B lands, so the API's "numbers without text" path works from day one.
  Rules and ML stubs raise NotImplementedError.

### Bright Data sample scrape

Dataset `gd_lfqkr8wm13ixtbd8f5` (Zillow properties listing information), the one linked for this project.

- Discovery by input filters (`discover_by=input_filters`, location + listingCategory) is refused with
  HTTP 400 "Customer is not active". Collect-by-URL works, and so does `discover_by=url` with a Zillow
  search URL (e.g. `https://www.zillow.com/san-diego-ca-92104/rentals/`), so the worker uses search URLs.
- A collect-by-URL test (an off-market condo in 92122): **yearBuilt came back (1993); priceHistory was null.**
- `discover_by=url` snapshot sd_mwh78b0y24gbxr2vwq (92104, limit 2 per input) returned 13 records in about
  4 minutes: 11 rentals and 2 for sale.
  - **For sale: priceHistory came back (1 to 12 events, including past sales) and yearBuilt came back (1911, 2012).**
  - **Rentals: priceHistory came back (10 or 11 events, with "Listed for rent", "Price change", "Listing removed")
    but yearBuilt was missing on every rental**, and nowhere else in the record. Ten units at one address shared
    the identical history, so for multi-unit buildings it describes the building's listing, not each unit.
  - Consequences: (1) the loader keeps a rental's history only when no other unit at the same address in the
    snapshot carries the same history; otherwise it's dropped, never attributed to a unit. (2) Year built for
    AB 1482 comes from a for-sale or off-market record at the same address (collect-by-URL returns yearBuilt)
    or from the tenant on the check form; when unknown, the verdict is `unclear` and the form asks for it.
    (3) Days on market in Owner mode can use the "Listed for rent" / "Listing removed" events where they exist.
  - `limit_per_input` is not a hard per-input cap: 2 requested, 11 rentals returned. Budget runs accordingly.

## Phase 3: integration

- **Merged:** lane/rules (54 tests), lane/models (73 tests total after merge).
- **Rent check with unknown year built:** lane B's engine treats the building as covered when `year_built`
  is null (the plan's decision order only exempts known-new buildings). This replaces the earlier note that an
  unknown year gives `unclear`; the form still asks for year built and prefills it from /units/search.
- **First real forecast run (2026-11-14):** 24 series (12 ZIPs × ZORI, ZHVI), median 12-month backtest MAPE
  1.38% (mean 1.65%), but the model beat the naive "next year equals this month" forecast on only 7 of 24.
  Per the plan, the UI shows the band and the backtest error under every chart, describes it as a trend
  range, and only says "beats naive" on the series where it does. Fair rent: skipped until rentals load.
