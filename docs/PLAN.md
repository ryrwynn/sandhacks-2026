# RentOrKnot: Architecture and Build Plan (SanD Hacks)

Nov 14, 2026 · @Ray

Accounts, keys and the Claude Code workflow are in the next tab: Setup and Claude Code

## Product: one data engine, three modes

RentOrKnot becomes a San Diego housing app with one shared data engine and three modes. Build the engine and Renter mode deep, Buyer mode solid and Owner mode thin. Three shallow products lose to one deep one, and the shared engine is what makes the other two cheap to add.

Pitch line: *know what San Diego housing should cost today, and what it will cost next year.*

| Mode | Who it's for | Questions it answers | Depth |
| --- | --- | --- | --- |
| Renter | Tenants, students, young renters | Is my increase legal? Is this listing overpriced? Where can I afford to live, and where is rent heading? | Deep: the demo and the Data for Good story |
| Buyer | First-time buyers and people building long-term wealth | Which ZIP codes fit my goal and budget? How are home values and rents expected to move? | Solid |
| Owner | Small landlords listing a unit | How do my listing's price and content compare with similar listings, and what's missing? Is a planned increase legal for my current tenant? | Thin: one screen |

The shared engine has two halves:

- **Data:** rental and for-sale listings from Bright Data; Zillow's rent and home-value indexes by ZIP; Census income by ZIP; OpenStreetMap amenity counts.
- **Analytics:** the AB 1482 rules (legal check), a fair-rent model (what a unit should rent for), 12-month forecasts of rent and home value per ZIP, and persona scores per ZIP.

How I read the pivot ideas (change these if I got one wrong):

- **"Optimal listing testing"** is an analysis, not a test run on any site. The Owner screen scores a listing the owner pastes in, or one already in the scraped data: where its price sits among comparable listings, what comparable listings state that it leaves out, and its predicted reach.
- **"Young people, cheap rent, few amenities"** is a Starter persona that ranks ZIPs by low rent and weights amenities lightly. **"Generational wealth investments"** is a Wealth builder persona that ranks ZIPs by expected appreciation and rental yield for buying.
- **Personas rank places by the user's goals and budget, never by who lives there.** Ranking neighborhoods by residents' age, race or family makeup can look like steering under fair housing law, and judges will ask.

**Scope: analysis only.** RentOrKnot reads public data and interprets it. It never posts, messages, applies or runs tests on any site. Anything it writes, such as the tenant's letter or a plain-language explanation, goes to the user to read or send themselves.

Build order: engine first, then Renter, Buyer and Owner. Each mode ships only after the one before it works end to end on the live server.

## Features by mode

Ten of the twelve features are core, and most reuse the same four analytics, so the core list is smaller than it looks. Priority is a dropdown; change it as the weekend goes.

| Mode | Feature | How it works | Data | Priority |
| --- | --- | --- | --- | --- |
| All | ZIP map | Map of 12 ZIP codes shaded by median rent, with the 12-month forecast change on hover | Listings, ZORI | Core |
| All | ZIP profile page | Rent and value history, forecasts with ranges, persona scores, amenity counts | Everything | Core |
| Renter | Rent increase check | AB 1482 rules decide whether an increase is over the cap | Tenant's numbers, building age from listings | Core |
| Renter | Reply letter | Gemini explains the verdict in 4 languages and drafts the English letter | Check result | Core |
| Renter | Listing price check | Fair-rent model gives an expected rent and range; flags listings above the range | Scraped rentals | Core |
| Renter | Rent forecast | 12-month forecast per ZIP with a range and its backtest error | ZORI | Core |
| Renter | Starter finder | Ranks ZIPs for cheap rent and short trips to basics, weighting other amenities lightly | Listings, ZORI, Census, OpenStreetMap | Core |
| Buyer | Wealth builder finder | Ranks ZIPs by expected appreciation, rental yield and budget fit | ZHVI, ZORI, for-sale listings | Core |
| Buyer | Custom weights | Sliders that re-rank ZIPs live | Persona scores | Stretch |
| Owner | Price position | Fair-rent estimate, percentile among comparable listings, and a reach score per price point | Scraped rentals | Core |
| Owner | Legal guardrail | For an occupied, covered unit, shows the maximum legal increase before suggesting a price | Rules engine | Core |
| Owner | Listing analysis | Scores the owner's listing for completeness, lists facts comparable listings state that it doesn't, and Gemini explains the gaps | Owner's text, comparable listings | Stretch |

## Prize tracks

The pivot strengthens Tiger Data (forecasting is a time-series problem) and keeps Bright Data and Best Overall as the main targets. Pitch Renter mode to the Bright Data judges, since their track is Data for Good; the investor features are the breadth story for Best Overall.

| Track | Prize | What the app uses it for | Priority |
| --- | --- | --- | --- |
| Bright Data: Data for Good | $1,000 / $750 / $500 to the top 3; $100 credits per team | Scrapes San Diego rental and for-sale listings, with price history and year built | Core |
| Best Overall Hack | Top award | Three modes on one engine; judged on design, functionality, innovation and presentation | Core |
| Tiger Data (MLH) | Stream Deck Mini | Hypertables for every price sighting and index value, continuous aggregates for medians, a forecasts table the API reads | Core |
| Gemini API (MLH) | MLH swag kits | Parses listings, explains verdicts and scores, drafts the letter, explains gaps in an owner's listing | Core |
| Vultr (MLH) | Assorted prizes | Hosts the API, worker and web app | Free add |
| GoDaddy Registry (MLH) | Digital gift card | Free domain from MLH for the live site; the track judges the name, so pick a short, memorable one | Free add |
| Cursor + Grok (SpaceXSI raffle) | Mechanical keyboard raffle | Build in Cursor and use Grok during the weekend | Free add |
| DEV Writing Challenge | $100 | Publish the build story after the event | Free add |
| ElevenLabs | Scale tier credits | Reads the Renter verdict aloud in Spanish, Vietnamese or Tagalog | Stretch |
| Mastra (MLH) | Retro computer speaker | A TypeScript "housing advisor" agent that calls the API as tools across modes | Stretch |

Still skip Neon (it would duplicate Tiger Data) and Solana. Stretch tracks wait until gate 3 in the build plan.

## Architecture

One Python worker loads four sources into Tiger Cloud and trains the models on a schedule. FastAPI holds the analytics engine and serves all three modes; Next.js is the only thing users see.

&#91;embedded content: Architecture · 4 sources, 1 engine, 3 modes\]

The worker and the API never call each other; the database is the only hand-off, so either can restart without breaking the other. Gemini only parses and writes, and every verdict, forecast and score comes from the engine inside FastAPI.

## Data sources

Only the Bright Data scrapes run on a schedule; everything else loads once at the start and is cached in the repo or the database, so the demo never depends on a third-party site being up.

| Source | What it provides | How it loads | Refresh | Key |
| --- | --- | --- | --- | --- |
| Bright Data Zillow scraper, rentals | Rent, beds, baths, sqft, year built, listing price history | `worker/run.py` for the 12 ZIP codes | Weekly, Thursday 12:00 UTC (was every 3 hours; see "Current state") | `BRIGHTDATA_API_TOKEN` |
| Bright Data Zillow scraper, for sale | List price, beds, sqft, year built, price history | Same worker, separate job | Daily | Same |
| [Zillow Research](https://www.zillow.com/research/data/) ZORI by ZIP | Monthly typical rent, years of history | CSV download, `db/load_zillow.py` | Once | None |
| [Zillow Research](https://www.zillow.com/research/data/) ZHVI by ZIP | Monthly typical home value, years of history | Same script | Once | None |
| Census ACS 5-year by ZIP area | Median household income (`B19013_001E`), median gross rent (`B25064_001E`) | One API call per variable for all San Diego ZIPs, `db/load_census.py` | Once | `CENSUS_API_KEY` (free) |
| OpenStreetMap (Overpass API) | Counts of grocery stores, transit stops, parks, cafes and restaurants, gyms per ZIP | One query per ZIP, saved to `data/amenities.json` | Once | None |
| Census ZIP boundaries | ZIP polygons for the map and amenity counting | GeoJSON saved to `web/public/zips.geojson` | Once | None |
| AB 1482 cap table | San Diego County caps with sources | `db/seed_caps.sql` | When the cap changes | None |
| Bright Data Facebook posts by group URL | Rental offers from 6 public San Diego housing groups (whole units, rooms, sublets), via Gemini extraction | `worker/facebook.py` | Mondays and Thursdays 15:00 UTC | Same as Zillow |

What this means for the earlier plan:

- The weekend-history problem mostly goes away. ZORI and ZHVI give years of monthly history per ZIP for trends and forecasts; scraped listings feed the fair-rent model and current comparisons.
- Test one rental and one for-sale listing through Bright Data in hour 1, and check whether `priceHistory` and `yearBuilt` come back for rentals; the Bright Data write-up only verified history on for-sale homes.
- Census ZIP areas (ZCTAs) and postal ZIP codes match for almost all residential ZIPs; drop any of the 12 that doesn't match rather than patching it.
- Run the Overpass queries once and commit the result. Repeated queries during the demo would be slow and unfair to a free public service.

## Source adapters

Every source enters through the same template: fetch raw records, map them to one canonical listing, then resolve and load. Adding Apartments.com or a public Facebook group is a YAML file and three fixture records, not a schema change. Adapters only read; nothing in the app posts, messages or tests anything on a source site.

1. **Fetch.** The adapter calls Bright Data (or downloads a file), drops the fields the template marks as personal, and stores each record in `raw_records`, keyed by source and content hash so re-runs don't duplicate.
2. **Map.** A per-source YAML template maps fields to the canonical listing. What the template can't map, such as the price and bedrooms inside a free-text post, goes to the Gemini parser. Every field records whether it was mapped or extracted, with a confidence.
3. **Clean.** Redact names, phone numbers and emails from text; turn "studio" into 0 bedrooms; keep rent ranges as a minimum and maximum; normalize addresses; set the location precision.
4. **Resolve.** Listings for the same unit on different sites (same normalized address, unit and bedroom count within 30 days) join one property. Listings without an address stay unattached and count only toward ZIP-level numbers.
5. **Load.** Write `listings` and `price_observations`, carrying the source's trust weight.

| Source key | Kind | How it's fetched | Mapping | Usual location precision | What it feeds |
| --- | --- | --- | --- | --- | --- |
| `zillow_rent` | Listing site | Bright Data Zillow Scraper API | Field map | Address | Everything: rules, fair-rent model, comparisons, history |
| `zillow_sale` | Listing site | Same | Field map | Address | Buyer mode, rental yield |
| `apartments_com` | Listing site | A custom scraper built in Bright Data's [AI Scraper Studio](https://brightdata.com/products/web-scraper/apartments-com-scraper); there's no prebuilt dataset, and 5,000 page loads a month are free | Field map, one record per floor plan | Address | Fair-rent model, comparisons |
| `facebook_groups` | Social | Bright Data's [Posts by group URL](https://docs.brightdata.com/api-reference/scrapers/social-media-apis/facebook-posts-by-group-collect-by-url.md) scraper, public groups only | Gemini extraction from post text | ZIP or neighborhood | ZIP-level medians at a lower weight; never building facts |
| `zillow_research` | Area index | CSV download | Column map to `area_metrics` | ZIP | Trends, forecasts |
| `census_acs` | Area statistics | Census API | Variable map | ZIP | Rent burden, context |
| `osm_amenities` | Area statistics | Overpass, cached | Tag map | ZIP | Persona scores |

The canonical listing every adapter must produce:

```python
# contracts/canonical.py
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Precision = Literal["address", "street", "zip", "neighborhood", "city"]

class CanonicalListing(BaseModel):
    source_key: str                        # 'zillow_rent', 'apartments_com', 'facebook_groups', ...
    external_id_hash: str                  # sha256 of the source's id; raw ids stay in raw_records
    listing_type: Literal["rent", "sale"]
    observed_at: datetime
    price_usd: int                         # monthly rent or sale price; the low end of a range
    price_max_usd: int | None = None       # the high end, when the source gives a range
    beds: int | None = None                # 0 = studio
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    property_type: str | None = None
    address_norm: str | None = None
    unit_label: str | None = None
    zip: str | None = None
    neighborhood: str | None = None
    lat: float | None = None
    lng: float | None = None
    location_precision: Precision
    text_redacted: str | None = None       # description with names, phones and emails removed
    extras: dict = Field(default_factory=dict)            # source-only fields: amenities, pet policy, floor plan
    field_confidence: dict[str, float] = Field(default_factory=dict)  # 1.0 = mapped; lower = extracted
    extraction: Literal["mapped", "llm", "mixed"] = "mapped"
```

Two example templates. You name the Apartments.com fields yourself when you build that scraper, so treat its field names as placeholders:

```yaml
# sources/apartments_com.yaml
source_key: apartments_com
kind: listing_site
fetch:
  method: brightdata_collector            # a scraper built in AI Scraper Studio
  collector_id: ${BRIGHTDATA_APARTMENTS_COLLECTOR}
  inputs: [{ url: "https://www.apartments.com/san-diego-ca-92104/" }]
listing_type: rent
explode: floor_plans                      # one canonical record per floor plan
map:
  external_id: id
  price_usd: floor_plan.rent_min
  price_max_usd: floor_plan.rent_max
  beds: floor_plan.beds
  baths: floor_plan.baths
  sqft: floor_plan.sqft_min
  address_norm: address
  zip: zip
  year_built: year_built
location_precision: address
trust_weight: 0.9
```

```yaml
# sources/facebook_groups.yaml
source_key: facebook_groups
kind: social
fetch:
  method: brightdata_dataset
  dataset_id: gd_lz11l67o2cb3r0lkj3        # Facebook posts by group URL
  inputs: [{ url: "https://www.facebook.com/groups/<public-group-id>" }]
drop_fields: [user_url, user_username_raw, profile_id, user_is_verified]   # never stored
listing_type: rent
map:
  external_id: post_id
  observed_at: date_posted
llm_extract:                              # Gemini reads `content`
  from: content
  fields: [price_usd, beds, baths, neighborhood, zip, is_rental_offer]
  keep_if: is_rental_offer                # skip "looking for a room" and unrelated posts
location_precision: zip
trust_weight: 0.5
```

To add a source:

1. Write `sources/<key>.yaml`.
2. Save three raw records to `contracts/fixtures/sources/<key>/`.
3. Run `uv run pytest api/tests/test_adapters.py -k <key>`; the golden test checks that each record maps to a valid `CanonicalListing` with no personal fields left.
4. Insert a row into `sources` with `enabled = true`. The worker picks it up on its next run.

Rules for social and community sources:

- Public groups only, and only after reading the site's terms and the group's rules. Bright Data's group scraper returns author fields (profile ID, username, profile URL); the template drops them before anything is stored.
- Post text is never shown in the app. Posts count only toward ZIP-level medians and counts, at a lower trust weight than listing sites.
- Store a hash of the post ID, never the post URL, so a stored row can't be traced back to a person.

## Data model

The schema doesn't know which site a row came from, beyond a `source_key` on every row. Three hypertables hold everything that changes over time (price sightings, area metrics, forecasts), and adding a source adds rows to `sources`, not new tables.

Design choices:

- **`sources` is the registry.** Each source is a row with its template path, trust weight, an on/off switch and the date someone checked its terms.
- **Properties and listings are separate.** A property is one physical unit, resolved across sites; a listing is one site's record of it. Building facts that decide AB 1482 coverage (year built) live on the property. A post without an address is a listing with no property and counts only toward its ZIP.
- **`area_metrics` is one long table for any number about an area.** ZORI, ZHVI, Census income and amenity counts load into it, and so would any new index, without new tables. `zip_features` is a view over its latest values.
- **`price_observations` copies ZIP, bedrooms, source and trust weight**, so the continuous aggregate reads one table and agents don't trip on join restrictions.
- **Comparisons use listing sites by default.** Social posts appear as a separate "posted asking rents" figure until you decide to trust them more.
- **Medians use the Toolkit's `percentile_agg`**, rolled up with `rollup` and read with `approx_percentile`. Exact weekly medians can't be combined into monthly ones; these summaries can ([Tiger Data docs](https://www.tigerdata.com/docs/reference/toolkit/percentile-approximation)).
- **`raw_records` keeps every response** (minus personal fields), so a mapping bug is fixed by re-running the template, not by scraping again.

```sql
-- db/migrations/001_init.sql
CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;

CREATE TABLE sources (
  source_key        TEXT PRIMARY KEY,          -- 'zillow_rent', 'apartments_com', 'facebook_groups', ...
  kind              TEXT NOT NULL,             -- 'listing_site' | 'social' | 'area_index' | 'area_stats'
  fetch_method      TEXT NOT NULL,             -- 'brightdata_dataset' | 'brightdata_collector' | 'csv' | 'api'
  template_path     TEXT NOT NULL,             -- sources/<key>.yaml
  trust_weight      NUMERIC(3,2) NOT NULL DEFAULT 1.0,
  enabled           BOOLEAN NOT NULL DEFAULT false,
  terms_checked_on  DATE
);

CREATE TABLE raw_records (
  id            BIGSERIAL PRIMARY KEY,
  source_key    TEXT NOT NULL REFERENCES sources,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  snapshot_id   TEXT,
  content_hash  TEXT NOT NULL,
  payload       JSONB NOT NULL,              -- personal fields already dropped
  UNIQUE (source_key, content_hash)
);

CREATE TABLE properties (                    -- one physical unit, resolved across sources
  property_id    BIGSERIAL PRIMARY KEY,
  address_norm   TEXT NOT NULL,
  unit_label     TEXT,
  zip            CHAR(5) NOT NULL,
  lat            DOUBLE PRECISION,
  lng            DOUBLE PRECISION,
  beds           SMALLINT,                   -- 0 = studio
  year_built     SMALLINT,                   -- decides AB 1482 coverage
  property_type  TEXT,                       -- 'apartment' | 'condo' | 'single_family'
  UNIQUE NULLS NOT DISTINCT (address_norm, unit_label, beds)
);

CREATE TABLE listings (                      -- one row per source listing or post
  listing_id          BIGSERIAL PRIMARY KEY,
  source_key          TEXT NOT NULL REFERENCES sources,
  external_id_hash    TEXT NOT NULL,
  property_id         BIGINT REFERENCES properties,   -- NULL when the location is too vague
  listing_type        TEXT NOT NULL,         -- 'rent' | 'sale'
  zip                 CHAR(5),
  neighborhood        TEXT,
  location_precision  TEXT NOT NULL,         -- 'address' | 'street' | 'zip' | 'neighborhood' | 'city'
  beds                SMALLINT,
  baths               NUMERIC(3,1),
  sqft                INTEGER,
  text_redacted       TEXT,
  extras              JSONB NOT NULL DEFAULT '{}',
  field_confidence    JSONB NOT NULL DEFAULT '{}',
  extraction          TEXT NOT NULL,         -- 'mapped' | 'llm' | 'mixed'
  first_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_key, external_id_hash)
);

CREATE TABLE price_observations (
  observed_at    TIMESTAMPTZ NOT NULL,
  listing_id     BIGINT NOT NULL REFERENCES listings,
  property_id    BIGINT,
  source_key     TEXT NOT NULL,
  listing_type   TEXT NOT NULL,
  zip            CHAR(5),
  beds           SMALLINT,
  price_usd      INTEGER NOT NULL,           -- monthly rent or sale price; low end of a range
  price_max_usd  INTEGER,
  trust_weight   NUMERIC(3,2) NOT NULL,
  event          TEXT NOT NULL,              -- 'history' | 'seen' | 'price_change' | 'removed' | 'posted'
  UNIQUE (listing_id, observed_at, event)
);
SELECT create_hypertable('price_observations', by_range('observed_at'));

CREATE TABLE area_metrics (                  -- any number about an area, from any source
  period      DATE NOT NULL,
  geo_type    TEXT NOT NULL,                 -- 'zip' today; 'tract' or 'neighborhood' later
  geo_id      TEXT NOT NULL,                 -- '92104'
  metric      TEXT NOT NULL,                 -- 'zori', 'zhvi', 'median_income', 'groceries', ...
  value       NUMERIC(14,2) NOT NULL,
  source_key  TEXT NOT NULL REFERENCES sources,
  PRIMARY KEY (geo_type, geo_id, metric, source_key, period)
);
SELECT create_hypertable('area_metrics', by_range('period'));

CREATE VIEW zip_features AS                  -- latest value of each metric, one row per ZIP
SELECT geo_id AS zip,
  max(value) FILTER (WHERE metric = 'median_income')   AS median_income_usd,
  max(value) FILTER (WHERE metric = 'acs_median_rent') AS acs_median_rent_usd,
  max(value) FILTER (WHERE metric = 'groceries')       AS groceries,
  max(value) FILTER (WHERE metric = 'transit_stops')   AS transit_stops,
  max(value) FILTER (WHERE metric = 'parks')           AS parks,
  max(value) FILTER (WHERE metric = 'food_drink')      AS food_drink,
  max(value) FILTER (WHERE metric = 'gyms')            AS gyms,
  max(value) FILTER (WHERE metric = 'area_km2')        AS area_km2
FROM (SELECT DISTINCT ON (geo_id, metric) geo_id, metric, value
      FROM area_metrics WHERE geo_type = 'zip'
      ORDER BY geo_id, metric, period DESC) latest
GROUP BY geo_id;

CREATE TABLE forecasts (
  run_id         UUID NOT NULL,
  made_at        TIMESTAMPTZ NOT NULL,
  month          DATE NOT NULL,              -- the month being forecast
  zip            CHAR(5) NOT NULL,
  metric         TEXT NOT NULL,              -- an area_metrics metric: 'zori' | 'zhvi'
  mean_usd       NUMERIC(12,2) NOT NULL,
  lo80_usd       NUMERIC(12,2),
  hi80_usd       NUMERIC(12,2),
  backtest_mape  NUMERIC(5,2),
  PRIMARY KEY (run_id, zip, metric, month)
);
SELECT create_hypertable('forecasts', by_range('month'));

CREATE MATERIALIZED VIEW listing_weekly_zip
WITH (timescaledb.continuous) AS
SELECT time_bucket('7 days', observed_at) AS week,
       zip, beds, listing_type, source_key,
       percentile_agg(price_usd) AS price_pct,
       count(*) AS n
FROM price_observations
WHERE zip IS NOT NULL
GROUP BY week, zip, beds, listing_type, source_key;

SELECT add_continuous_aggregate_policy('listing_weekly_zip',
  start_offset => INTERVAL '3 years',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '30 minutes');

CREATE TABLE model_runs (
  run_id         UUID PRIMARY KEY,
  kind           TEXT NOT NULL,              -- 'fair_rent' | 'forecast'
  trained_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  n_rows         INTEGER,
  sources_used   TEXT[],                     -- which source_keys trained it
  metrics        JSONB,                      -- MAE, MAPE, coverage of the 80% range
  artifact_path  TEXT
);

CREATE TABLE rent_caps (
  region        TEXT NOT NULL,               -- 'san_diego_county'
  period_start  DATE NOT NULL,
  period_end    DATE NOT NULL,
  cap_pct       NUMERIC(4,2) NOT NULL,       -- 8.20 means 8.2%
  source_url    TEXT NOT NULL,
  PRIMARY KEY (region, period_start)
);

CREATE TABLE rent_checks (
  check_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  address           TEXT NOT NULL,
  zip               CHAR(5),
  lowest_rent_12mo  INTEGER NOT NULL,
  new_rent          INTEGER NOT NULL,
  effective_date    DATE NOT NULL,
  year_built        SMALLINT,
  verdict           TEXT NOT NULL,           -- 'over_cap' | 'within_cap' | 'not_covered' | 'unclear'
  max_legal_rent    INTEGER,
  is_demo           BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE listing_analyses (              -- Owner mode, read-only analysis
  analysis_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  input        JSONB NOT NULL,               -- unit facts, the owner's listing text, target rent
  results      JSONB NOT NULL,               -- price position, completeness, gaps vs. comparables
  is_demo      BOOLEAN NOT NULL DEFAULT false
);
```

```sql
-- db/seed_sources.sql  (social and custom-scraper sources start disabled)
INSERT INTO sources (source_key, kind, fetch_method, template_path, trust_weight, enabled) VALUES
  ('zillow_rent',     'listing_site', 'brightdata_dataset',   'sources/zillow_rent.yaml',     1.0, true),
  ('zillow_sale',     'listing_site', 'brightdata_dataset',   'sources/zillow_sale.yaml',     1.0, true),
  ('apartments_com',  'listing_site', 'brightdata_collector', 'sources/apartments_com.yaml',  0.9, false),
  ('facebook_groups', 'social',       'brightdata_dataset',   'sources/facebook_groups.yaml', 0.5, false),
  ('zillow_research', 'area_index',   'csv',                  'sources/zillow_research.yaml', 1.0, true),
  ('census_acs',      'area_stats',   'api',                  'sources/census_acs.yaml',      1.0, true),
  ('osm_amenities',   'area_stats',   'api',                  'sources/osm_amenities.yaml',   1.0, true);
```

The query behind every trend chart joins history and the latest forecast:

```sql
WITH latest AS (
  SELECT run_id FROM model_runs WHERE kind = 'forecast' ORDER BY trained_at DESC LIMIT 1
)
SELECT period AS month, value, NULL::numeric AS lo80, NULL::numeric AS hi80, 'actual' AS kind
FROM area_metrics
WHERE geo_type = 'zip' AND geo_id = %(zip)s AND metric = %(metric)s
  AND source_key = 'zillow_research' AND period >= now() - INTERVAL '5 years'
UNION ALL
SELECT f.month, f.mean_usd, f.lo80_usd, f.hi80_usd, 'forecast'
FROM forecasts f JOIN latest USING (run_id)
WHERE f.zip = %(zip)s AND f.metric = %(metric)s
ORDER BY month;
```

## Rent-cap detection logic

The legal check is a plain Python function with no AI in it. It takes the tenant's lowest rent in the past 12 months, the new rent, the date the increase takes effect and a few building facts, and returns a verdict and the maximum legal rent. For San Diego County the cap is 8.2% for increases effective Aug 1, 2026 through Jul 31, 2027, and was 8.8% the year before ([Goodlife](https://www.goodlifemgmt.com/blog/california-rent-cap-2026/)).

```latex
\text{max legal rent} = R_{\text{lowest, past 12 mo}} \times \left(1 + \min(5\% + \Delta\text{CPI}_{\text{San Diego}},\ 10\%)\right)
```

Rules from [Civil Code 1947.12](https://california.public.law/codes/ca_civ_code_section_1947.12) the function has to encode:

- The baseline is the lowest rent charged in the 12 months before the increase, not last month's rent, and accepted discounts don't count.
- Rent can rise in at most two steps in any 12 months for the same tenant.
- A new tenancy's starting rent isn't capped; only later increases are.
- The CPI is San Diego-Carlsbad CPI-U, April to April, and the yearly cap switches on Aug 1.
- The law sunsets on Jan 1, 2030.

Decision order (stop at the first verdict):

1. **Age exemption.** Buildings with a certificate of occupancy in the past 15 years are exempt. Use `year_built` as a proxy: newer than 15 years → `not_covered`; within a year of the line → `unclear`, since year built and certificate date can differ.
2. **Single-family home or condo.** Exempt only if the owner isn't a corporation, REIT or LLC with a corporate member, and the tenant got the written exemption notice. Ask: "Does your lease say the property is not subject to the rent limits of Civil Code 1947.12?" Yes → `not_covered`; no → covered; don't know → `unclear`.
3. **Other exemptions**, one checkbox: owner lives in the other half of a duplex, a school dorm, or income-restricted affordable housing → `not_covered`.
4. **Cap lookup.** Pick the `rent_caps` row whose period contains the effective date.
5. **Compare.** New rent above the maximum → `over_cap` with the overage per month and per year; otherwise `within_cap`. Separately flag a third increase within 12 months.

Demo case: lowest rent $2,100, new rent $2,350 (+11.9%) effective Dec 1, 2026, in a 1978 apartment building. The cap is 8.2%, so the maximum is $2,272.20 and the increase is $77.80 a month over, $933.60 a year.

```python
# api/rules/ab1482.py
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass(frozen=True)
class CheckInput:
    lowest_rent_12mo: Decimal
    new_rent: Decimal
    effective_date: date
    year_built: int | None
    property_type: str                 # 'apartment' | 'condo' | 'single_family' | 'unknown'
    got_exemption_notice: bool | None  # None = tenant doesn't know
    owner_is_corporate: bool | None
    other_exemption: bool              # duplex owner on site, dorm, income-restricted
    increases_last_12mo: int

@dataclass(frozen=True)
class CheckResult:
    verdict: str                       # 'over_cap' | 'within_cap' | 'not_covered' | 'unclear'
    cap_pct: Decimal | None
    max_legal_rent: Decimal | None
    overage_monthly: Decimal | None
    reasons: list[str]                 # plain-language lines, shown in the UI and passed to Gemini

def check_increase(inp: CheckInput, caps: list["RentCap"]) -> CheckResult: ...
```

Write these tests before the function, so an agent has a clear target: the demo case above; an increase exactly at the cap; a 2015 building; a building right at the 15-year line; a condo with and without the notice; effective dates on Jul 31 and Aug 1, 2026 (different caps); and a third increase in 12 months. Use `Decimal`, not floats, and round down to the cent.

Scraped listings feed a separate, clearly labeled market signal: units that relisted far above their last price. That is not a violation, because a new tenant's starting rent isn't capped, so the UI calls it a trend, never a legal finding. Every verdict screen says it isn't legal advice and points to Legal Aid Society of San Diego.

## Prediction and scoring

Four pieces of plain, explainable math sit beside the rules engine: a fair-rent model, ZIP forecasts, persona scores and a listing analysis. Every number shown to a user comes with a range or its measured error, because a confident wrong prediction is the fastest way to lose judges.

### Fair-rent model

Predicts what a rental should list for from its facts, with an 80% range. It powers the Renter listing check, the Owner price position and the yield estimate for buyers.

- **Training data:** the latest price of each rental listing with an address-level location from listing-site sources (`zillow_rent`, `apartments_com`), weighted by each source's trust weight. Social posts are left out because they rarely state size or address. Features: beds, baths, log sqft, ZIP (categorical), year built, property type, lat and lng. Target: log rent.
- **Model:** scikit-learn `HistGradientBoostingRegressor` with `loss="quantile"`, fitted three times (10th, 50th and 90th percentiles).
- **Validation:** 5-fold cross-validation grouped by building, so units in one building never sit on both sides. Report median absolute error in dollars and how often held-out rents land inside the 80% range (it should be close to 80%).
- **Labels:** above the 90th-percentile estimate → "above typical range"; between → "in range"; below → "below typical range". Never "illegal": that word belongs to the rules engine.
- **Fallback:** under about 1,000 rentals, use the ZIP-and-bedroom median from `listing_weekly_zip` with its spread instead, and say so on screen.

```python
# api/ml/fair_rent.py
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ["beds", "baths", "log_sqft", "zip_code", "year_built", "ptype_code", "lat", "lng"]

def fit(df):
    X, y = df[FEATURES], np.log(df["rent"])
    cat = [FEATURES.index("zip_code"), FEATURES.index("ptype_code")]
    return {q: HistGradientBoostingRegressor(loss="quantile", quantile=q, categorical_features=cat,
                                             max_iter=300, learning_rate=0.05).fit(X, y)
            for q in (0.1, 0.5, 0.9)}

def predict(models, row):
    lo, mid, hi = (float(np.exp(models[q].predict(row[FEATURES])[0])) for q in (0.1, 0.5, 0.9))
    return {"low": lo, "expected": mid, "high": hi}
```

### Rent and home-value forecasts

Forecasts 12 months ahead for each ZIP, for rent (ZORI) and home value (ZHVI), and stores them in `forecasts`.

- **Model:** statsmodels `ETSModel` on log values, additive damped trend. Add a 12-month seasonal term only if the downloaded series isn't already seasonally adjusted.
- **Range:** the 80% prediction interval from `get_prediction(...).summary_frame(alpha=0.2)`.
- **Backtest:** refit with the last 12 months held out and record the error (MAPE). Also score a naive "next year equals this month" forecast; only claim the model beats it if it does.
- **Display:** history as a solid line, forecast as a dashed line with a shaded band, and the backtest error printed under the chart.

```python
# api/ml/forecast.py
import numpy as np
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

def forecast_12(series):  # monthly pandas Series of dollar values, DatetimeIndex
    fit = ETSModel(np.log(series), error="add", trend="add", damped_trend=True).fit(disp=False)
    frame = fit.get_prediction(start=len(series), end=len(series) + 11).summary_frame(alpha=0.2)
    return np.exp(frame[["mean", "pi_lower", "pi_upper"]])
```

### Persona scores

Each ZIP gets a 0 to 100 score per persona from price, forecast and amenity features. Every feature is min-max scaled across the 12 ZIPs, flipped where lower is better, then weighted. The user's budget is a hard filter: ZIPs above it move to a separate "stretch" list.

| Feature (per ZIP) | Starter renter | Wealth builder |
| --- | --- | --- |
| Typical rent for the chosen bedroom count (lower is better) | 0.40 |  |
| Forecast rent change, next 12 months (lower is better) | 0.20 |  |
| Basics nearby: groceries and transit stops per km² | 0.25 |  |
| Other amenities: food and drink, gyms, parks per km² | 0.05 |  |
| Listings available in the last 30 days | 0.10 |  |
| Forecast home-value change, next 12 months |  | 0.35 |
| Gross rental yield (12 × typical rent ÷ typical home value) |  | 0.30 |
| Typical home value against budget |  | 0.20 |
| Price volatility, 5-year standard deviation of monthly changes (lower is better) |  | 0.15 |

- Weights are starting guesses; the custom-weights sliders (stretch) let users change them.
- The response includes the three features that contributed most, which Gemini turns into two plain sentences.
- Rent burden (typical rent ÷ monthly median household income) appears on the ZIP page as context, not as a score input.
- No feature describes who lives in a ZIP. Scores use prices, forecasts, listings and amenities only.

### Listing analysis (Owner mode)

A read-only analysis of one listing, before or after it goes live: where its price sits, how complete it is, and what comparable listings state that it doesn't. It is a prediction, not measured clicks, and the screen says so.

1. **Price points:** the fair-rent low, expected and high estimates plus the owner's target. For each, show its percentile among comparable active listings (same ZIP and bedroom count). For example, "cheaper than 70% of comparable 2-bedrooms in 92104."
2. **Days on market (if the data allows):** if Bright Data's rental history includes listing and removal events, show the median days listed for units priced below and above the expected rent. If not, leave this out.
3. **Legal guardrail:** if the unit is occupied and covered by AB 1482, show the maximum legal rent for the current tenant before any suggestion.
4. **Listing analysis:** the owner pastes their listing text, or picks one already in the scraped data. It gets a completeness score (does it state price, beds, baths, sqft, pets, parking, laundry, utilities and move-in date?), a readability score, and a list of facts most comparable listings state that this one doesn't. Gemini explains the gaps in plain words; it never writes a replacement listing. Reach score = completeness × a price-position factor.

## Gemini roles

Gemini turns data into fields and numbers into words in all three modes; it never produces a verdict, a forecast or a score. Every dollar figure or percentage it writes must already exist in the engine's output, or the text is regenerated.

| Job | Mode | Input → output | Model tier |
| --- | --- | --- | --- |
| Listing parser | Engine | Listing description or social post, plus any mapped fields → JSON with beds, baths, sqft, year built, unit label, property type, pets, parking, laundry | Flash |
| Verdict explainer | Renter | Check result → 3 to 5 sentences in English, Spanish, Vietnamese or Tagalog | Flash |
| Letter drafter | Renter | Check result, names, address → formal English letter citing Civil Code 1947.12 | Flash (Pro only if your key's quota allows) |
| "Why this ZIP" summary | Renter, Buyer | A ZIP's top 3 score contributions → 2 plain sentences | Flash |
| Listing gap explainer | Owner | The owner's listing and the gaps found → 2 to 4 plain sentences on what's missing and why it matters; never a rewritten listing | Flash |

Set `PARSE_MODEL` (Flash tier) and `LETTER_MODEL` (Flash works; Pro returned 429 on a free-tier key) in `.env` from the current model list in Google AI Studio, so a model rename is a config change.

Pin exact model names that returned HTTP 200 for your key (test them as in the Setup tab), not `-latest` aliases, which can return HTTP 503 when demand spikes. Older names such as `gemini-2.5-flash` aren't offered to new keys. `api/llm/gemini.py` retries a 503 or 429 three times with backoff (1, 2 and 4 seconds), then tries `GEMINI_FALLBACK_MODEL` once. If that fails too, the page shows the verdict, forecast or score without the generated text; nothing the user needs depends on Gemini answering.

```python
# api/llm/gemini.py
import os, re
from google import genai
from google.genai import types
from pydantic import BaseModel

client = genai.Client()  # reads GEMINI_API_KEY

class ListingFields(BaseModel):
    beds: int | None
    baths: float | None
    sqft: int | None
    year_built: int | None
    unit_label: str | None
    property_type: str | None   # 'apartment' | 'condo' | 'single_family'
    pets_allowed: bool | None
    parking: bool | None
    in_unit_laundry: bool | None

def parse_listing(text: str) -> ListingFields:
    resp = client.models.generate_content(
        model=os.environ["PARSE_MODEL"],
        contents="Extract these fields from the rental listing. Use null when a field isn't stated.\n\n" + text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ListingFields,
            temperature=0,
        ),
    )
    return resp.parsed

NUMBER = re.compile(r"\$[\d,]+(?:\.\d{2})?|\d+(?:\.\d+)?%")

def figures_ok(text: str, allowed: set[str]) -> bool:
    """Reject text that mentions a dollar amount or percentage the engine didn't produce."""
    return set(NUMBER.findall(text)) <= allowed
```

For judges, show one messy listing next to its parsed JSON, and one Spanish explanation next to the numbers it came from.

## API contract and pages

FastAPI serves 12 endpoints under `/api`, and Next.js has 7 pages. Caddy sends `/api/*` to FastAPI (prefix stripped) and everything else to Next.js, so the browser talks to one domain and there's no CORS to debug.

| Endpoint | Returns | Used by |
| --- | --- | --- |
| `GET /health` | Database status, last scrape time, row counts, latest model runs | Debugging, demo |
| `GET /zips` | The 12 ZIPs: name, median rent by bedrooms (last 30 days), 12-month rent and value forecast change | Map |
| `GET /zips/{zip}` | ZIP profile: features, persona scores, amenity counts, rent burden | ZIP page |
| `GET /zips/{zip}/series?metric=zori\|zhvi` | Monthly history plus the latest forecast with its 80% band and backtest error | Trend charts |
| `POST /checks` | Rent-increase verdict, cap, maximum legal rent, reasons | Renter |
| `POST /checks/{id}/letter?lang=es` | Explanation in the chosen language and the English letter | Renter letter page |
| `GET /units/search?address=` | Matching units with year built and property type | Prefills forms |
| `POST /listings/evaluate` | Expected rent with low and high, label, percentile among comparable listings | Renter listing check |
| `POST /neighborhoods/rank` | Ranked ZIPs for a persona, budget and bedroom count, with top-3 contributions, a summary and a stretch list | Renter (Starter), Buyer (Wealth builder) |
| `POST /owner/price-position` | Price points with percentiles, days on market if available, legal maximum if the unit is occupied | Owner |
| `POST /owner/listing-analysis` | Completeness, readability and reach scores, gaps against comparable listings, and a plain explanation | Owner |
| `GET /openapi.json` | The contract itself, for generating the TypeScript client | Web build |

| Page | What's on it |
| --- | --- |
| `/` | Pick a mode; ZIP map shaded by median rent, forecast change on hover |
| `/renter` | Two tabs: Check my increase, Check a listing (the Starter finder moved into `/find`) |
| `/renter/letter/[id]` | Printable letter and the explanation in the chosen language |
| `/buyer` | Wealth builder finder: budget and bedrooms in, ranked ZIPs and map highlights out |
| `/owner` | Price position table, legal guardrail, listing analysis |
| `/zip/[zip]` | Rent and value charts with forecast bands, persona scores, amenities, rent burden |
| `/about` | Data sources, model errors, "not legal or financial advice" |

Shared components: `ZipMap` (MapLibre via `react-map-gl`), `ForecastChart` (Recharts line with a shaded band), `ScoreCard`, `VerdictCard`, `ListingCheckCard`, `ListingAnalysisCard`. Forms are client components that call the API through the generated client in `web/lib/api.ts`; everything else renders on the server.

## Repo layout and agent lanes

Write the contracts by hand first, then give each agent one lane that owns its own folders. Six lanes: five for agents and one for a person who owns deployment and the demo.

```text
rentorknot/
├─ CLAUDE.md                # short rules every agent reads (Setup tab, step 3)
├─ docs/PLAN.md             # this Plan tab, exported as Markdown
├─ .env.example
├─ docker-compose.yml       # api, worker, web, caddy
├─ Caddyfile                # /api/* → api (prefix stripped), everything else → web
├─ .github/workflows/deploy.yml
├─ scripts/                 # deploy.sh, smoke.sh
├─ sources/                 # one YAML template per source
│  ├─ zillow_rent.yaml
│  ├─ zillow_sale.yaml
│  ├─ apartments_com.yaml   # ships disabled
│  ├─ facebook_groups.yaml  # ships disabled
│  ├─ zillow_research.yaml  # ZORI and ZHVI CSVs → area_metrics
│  ├─ census_acs.yaml
│  └─ osm_amenities.yaml
├─ contracts/
│  ├─ canonical.py          # CanonicalListing: what every adapter must produce
│  ├─ api_models.py         # Pydantic models: the source of the OpenAPI schema
│  └─ fixtures/             # one JSON response per endpoint; sources/<key>/ raw samples
├─ data/                    # amenities.json, zips.txt, downloaded CSVs
├─ db/
│  ├─ migrations/001_init.sql
│  ├─ seed_caps.sql
│  └─ seed_sources.sql
├─ worker/
│  ├─ run.py                # for each enabled source: fetch → map → clean → resolve → load
│  ├─ adapters/             # brightdata_dataset.py, brightdata_collector.py, csv_file.py, http_api.py
│  ├─ mapping.py            # applies a YAML template to a raw record
│  ├─ llm_extract.py        # Gemini fills fields a template can't map
│  ├─ redact.py             # drops personal fields, redacts names, phones, emails
│  ├─ resolve.py            # joins listings for the same unit into one property
│  └─ train.py              # nightly: fair-rent model, forecasts, model_runs rows
├─ api/
│  ├─ main.py
│  ├─ routers/              # health, zips, checks, listings, neighborhoods, owner
│  ├─ rules/ab1482.py
│  ├─ ml/                   # fair_rent.py, forecast.py, scoring.py, listing_analysis.py
│  ├─ llm/gemini.py
│  └─ tests/                # includes test_adapters.py (golden tests per source)
└─ web/                     # Next.js app router, Tailwind, shadcn/ui
   ├─ app/                  # /, /renter, /buyer, /owner, /zip/[zip], /about
   ├─ components/
   ├─ lib/api.ts            # generated from /api/openapi.json
   └─ mocks/                # serves contracts/fixtures until the API is live
```

| Lane | Owns | Done when |
| --- | --- | --- |
| A: Data | `worker/` (except `train.py`), `db/`, `data/` | Rentals and for-sale listings for 12 ZIPs in Tiger; ZORI, ZHVI, Census and amenities loaded; `cron` running |
| B: Rules + Gemini | `api/rules/`, `api/llm/` | All rule tests pass; letters, summaries and gap explanations pass `figures_ok` on fixtures |
| C: Models | `api/ml/`, `worker/train.py` | Fair-rent model trained with its CV error saved; forecasts written with backtests; scoring tests pass |
| D: API | `api/main.py`, `api/routers/` | Every endpoint returns fixture-shaped data from the database; `/api/docs` works |
| E: Web | `web/` | All 7 pages work against mocks, then against the live API, on a phone-sized screen |
| F: Ops + demo (a person) | Compose, Caddy, domain, Vultr, GitHub Actions, demo script | Skeleton live on the domain by hour 4; auto-deploy and smoke test on every push |

Rules for every agent (the full `CLAUDE.md` is in the Setup tab):

- Read `contracts/` before coding; never edit `contracts/` or `db/migrations/` without saying why in the commit.
- Stay inside your lane's folders; run your lane's tests before saying done.
- Commit small and push often; one person merges lanes into `main` every 2 hours.
- Never read or print `.env`. Log every Bright Data and Gemini call with status and duration.
- If the same error comes back twice, stop and write down what you tried.

Give each lane its own git worktree (`git worktree add ../rw-web lane/web`) so agents never edit the same checkout. After any contract change, regenerate the web client from `/api/openapi.json`.

## Build plan

Five phases with three gates, built in mode order. If a gate slips, cut scope from the next phase rather than moving the gate: a live Renter flow at hour 8 matters more than any feature after it.

&#91;embedded content: Build plan · 5 phases, 3 gates\]

Letters match the lanes: A data, B rules and Gemini, C models, D API, E web, F ops and demo. Tick items off as you go.

### Hours 0 to 2: contracts and spikes

- [ ] All: pick lanes; create the repo, `CLAUDE.md` and `.env` (Setup tab); claim credits and the MLH GoDaddy domain
- [ ] A: create the Tiger Cloud service, run `001_init.sql`, seed `rent_caps`
- [ ] A: scrape one rental and one for-sale listing; check for `priceHistory` and `yearBuilt`
- [ ] A: start discovery runs for the 12 ZIP codes (rent and sale); download the ZORI and ZHVI CSVs
- [ ] D (a person, not an agent): write `contracts/api_models.py` and one fixture per endpoint
- [ ] F: Vultr server up and the domain pointed at it
- [ ] Gate 1: listings arriving, schema in place, Zillow indexes loaded

### Hours 2 to 8: engine lanes in parallel

- [ ] A: normalizer and loaders (rentals, sales, ZORI, ZHVI, Census, amenities); `cron` every 3 hours
- [ ] B: rule tests first, then `check_increase`; Gemini parser and explainer
- [ ] C: forecasts with backtests written to `forecasts`; scoring function with tests
- [ ] D: `/health`, `/checks`, `/units/search` and `/zips` against the database
- [ ] E: rent increase flow and ZIP map against mocks, phone-first
- [ ] F: skeleton live on the domain by hour 4; auto-deploy and smoke test on every push
- [ ] Gate 2: the rent check works on the live domain

### Hours 8 to 13: Renter mode

- [ ] C: fair-rent model trained once enough rentals exist; cross-validation error saved
- [ ] B: letter drafter with `figures_ok`; "why this ZIP" summaries
- [ ] D: `/listings/evaluate`, `/neighborhoods/rank` (Starter) and `/zips/{zip}/series`
- [ ] E: listing check, Starter finder, ZIP page with forecast bands, letter page

### Hours 13 to 18: Buyer and Owner

- [ ] D and E: Wealth builder finder at `/buyer`
- [ ] C, D and E: Owner price position and legal guardrail at `/owner`
- [ ] B: listing gap explanations with completeness and readability scores, only if on schedule
- [ ] All: full click-through on a phone; seed the example checks with `is_demo = true`
- [ ] Gate 3: all three modes live with real data; freeze features

### Hours 18 to 24: demo and submit

- [ ] Stretch, only after gate 3: custom weights, ElevenLabs voice, Mastra advisor agent
- [ ] Record a backup demo video
- [ ] Write the submission and list every track, including GoDaddy Registry
- [ ] Rehearse the 3-minute demo twice
- [ ] Submit, and draft the DEV post for after the event

## Demo script and judging angles

Tell it as three San Diegans with one question, in 3 minutes, on the live domain. Renter mode gets the most time because it carries the Data for Good story; Owner mode gets 15 seconds.

1. **0:00 to 0:20, hook.** "Three people, one question: what should housing in San Diego cost today, and what will it cost next year?"
2. **0:20 to 1:20, Maria, a renter in City Heights.** Her rent goes from $2,100 to $2,350 on Dec 1, 2026. RentOrKnot finds her 1978 building, applies the 8.2% cap and shows a $2,272.20 maximum, $77.80 a month over. Switch the explanation to Spanish and print the letter. Then paste a 2-bedroom listing she's considering: "above typical range" with the expected rent and range.
3. **1:20 to 1:55, Jordan, 23, first apartment.** Starter persona, $1,900 budget, studio or 1-bedroom: ranked ZIPs with plain reasons. Open the top ZIP: rent history, a dashed forecast with its band, and the backtest error underneath.
4. **1:55 to 2:30, Linda, buying to build long-term wealth.** Wealth builder persona, $750,000 budget: ZIPs ranked by expected appreciation and rental yield, with a stretch list above budget. Open one ZIP's home-value forecast.
5. **2:30 to 2:45, an owner listing a unit.** Price position table, then the analysis of their listing: completeness score and what comparable listings mention that it doesn't.
6. **2:45 to 3:00, close.** One data engine, three modes, live on its own domain; then the data sources and what's next.

| Track | Show | Say |
| --- | --- | --- |
| Bright Data: Data for Good | `/api/health` row counts, a raw snapshot, Maria's flow | Public web data turned into a legal check and a fair-price check any renter can run |
| Tiger Data | The three hypertables, the continuous aggregate, the forecast query and its time on screen | Every sighting and index value is a row; forecasts live next to history and are queried the same way |
| Gemini | A messy listing next to its JSON; the Spanish explanation; the figure check | Gemini handles words; the numbers come from tested code |
| Vultr | The site served from the Vultr server; `docker compose ps` | The whole stack runs on one server, deployed on every push |
| GoDaddy Registry | The domain in the browser bar | A name people can remember and type on a phone |
| Best Overall | All three personas, the design, the phone layout | One engine, three useful products |

Questions to prepare for:

- **"How accurate are the forecasts?"** Point to the backtest error printed under each chart, and whether the model beat the naive forecast.
- **"Isn't recommending neighborhoods by age a fair housing problem?"** Personas rank by the user's goals and budget; no score uses who lives in a ZIP.
- **"Isn't a big jump on a relisted unit illegal?"** No. A new tenant's starting rent isn't capped, so that's a market label, not a legal finding.
- **"Is this financial advice?"** No. It shows estimates with ranges and sources, and the About page says so.

## Risks and fallbacks

The pivot's biggest new risk is scope: three modes can turn into three half-built apps. The build order and gates exist to stop that; every other risk has a fallback that keeps the demo working.

| Risk | Early warning | Fallback |
| --- | --- | --- |
| Three modes, none finished | Renter mode isn't live end to end by hour 12 | Cut Owner mode to the price-position table; cut Buyer to the ranked list without the ZIP forecast page |
| Too few rentals for the fair-rent model | Under about 1,000 rentals after the first scrape runs | Use ZIP-and-bedroom medians with their spread, and say so on screen |
| Forecasts look confident but are wrong | Backtest error is high, or the naive forecast wins | Show the band and the error prominently; describe it as a trend range, not a prediction |
| Bright Data runs are slow or fail | The San Diego discovery run isn't done by hour 2 | Send listing URLs in batches of 20, retry failed rows, ask the Bright Data mentors; Zillow indexes still carry the charts |
| Rental listings return no price history | The hour 1 test listing has no history events | Drop days-on-market from Owner mode; everything else still works |
| Fair-housing question from judges | A persona or score uses resident demographics | Remove that feature; scores use prices, forecasts, listings and amenities only |
| Tiger Cloud setup trouble | The migration fails in hour 1 | Run the `timescale/timescaledb-ha` Docker image on the Vultr server with the same SQL; confirm the Toolkit extension loads |
| Gemini invents numbers or features | `figures_ok` fails, or an explanation mentions a fact that isn't in the data | Regenerate once, then fall back to a template with the numbers filled in |
| Domain or HTTPS not working | The domain doesn't resolve to the server by hour 6 | Demo from the server's IP over HTTP and fix DNS in parallel |
| Late deployment surprises | First real deploy happens after hour 18 | Skeleton live by hour 4, auto-deploy on every push, backup video recorded at hour 20 |

## Sources

- [SanD Hacks MLH prize tracks](https://www.mlh.com/events/sand-hacks/prizes)
- [California rent cap 2026: San Diego 8.2% (Goodlife)](https://www.goodlifemgmt.com/blog/california-rent-cap-2026/)
- [California Civil Code 1947.12](https://california.public.law/codes/ca_civ_code_section_1947.12)
- [How to scrape Zillow (Bright Data)](https://brightdata.com/blog/web-data/how-to-scrape-zillow.md)
- [Bright Data quickstart](https://docs.brightdata.com/quickstart.md)
- [Percentile approximation (Tiger Data docs)](https://www.tigerdata.com/docs/reference/toolkit/percentile-approximation)
- [UddSketch and percentile\_agg (Tiger Data docs)](https://www.tigerdata.com/docs/reference/toolkit/percentile-approximation/uddsketch)
- [Tiger Cloud 5-minute quickstart](https://www.tigerdata.com/docs/get-started/quickstart/quickstart-5-minutes)
- [Zillow Research housing data (ZORI, ZHVI)](https://www.zillow.com/research/data/)
- [Using Gemini API keys](https://ai.google.dev/gemini-api/docs/api-key)

* [Bright Data: Facebook posts by group URL](https://docs.brightdata.com/api-reference/scrapers/social-media-apis/facebook-posts-by-group-collect-by-url.md)
* [Bright Data: Apartments.com scraper (AI Scraper Studio)](https://brightdata.com/products/web-scraper/apartments-com-scraper)

Bright Data, ElevenLabs, Neon and Best Overall track details come from the SanD Hacks track list you shared earlier.

## Current state (final run, 2026-11-15)

What is true now, where it differs from the plan above:

- **Zillow refresh.** `zillow_rent` runs weekly (Thursday 12:00 UTC = 4:00 AM PST, 5:00 AM during daylight time);
  `zillow_sale` daily. Bright Data's `limit_per_input` isn't a hard cap (a run delivered ~1,777 records), so 3-hourly
  runs would cost ~$640 a month; weekly is ~$12. A listing is active when seen in its source's latest scrape (latest
  `last_seen` minus 36 hours), which works for any schedule. The UI says "Updated weekly".
- **Facebook listings** (`facebook_groups_sd`). Six public San Diego groups. Only post id, URL, text, date and group are
  read; text is redacted, sent to Gemini (`parse_posts`, 10 posts per Flash Lite request) and never stored. A post becomes
  a listing when it offers a place with a price, bedrooms and a resolvable San Diego ZIP: whole units, sublets, and rooms
  in a shared home ("roommate wanted"; `extras.roommate_wanted`). People looking for a place stay out. Listings keep a
  link to the post (`post_url`), extracted amenities and a price history: reposts within 30 days are `posted` or
  `price_change` observations on one listing; inactive 21 days after the last post. Location precision is the ZIP.
- **Source breakdown and weighting.** Medians and counts use listing sites at weight 1 and Facebook whole units at 0.5;
  rooms, sublets and unusual prices (below 40% or above 250% of the ZIP's listing-site median) never. Market and ZIP
  responses carry a per-source breakdown and accept `listing_sites_only=true`. Facebook rows never train the fair-rent
  model, never create building facts, and rooms get no fair-rent label.
- **12-ZIP guard.** Every live market, listing, median, comparable and `zip_features` query in `api/db.py` filters to
  `data/zips.txt` (`CORE_ZIPS`); other areas stay in staging tables (`staging_listings`, `staging_area_metrics`).
- **Card tags.** `ListingSummary.tags` (at most 4): listing amenities first (Zillow unit amenities: washer/dryer,
  dishwasher, hardwood floors; Facebook: parking, laundry, pets allowed, utilities included), then area tags from
  `zip_features` when the ZIP is in the top third of the 12 per km² ("Groceries nearby (ZIP)", transit stops, parks).
  Facebook rooms show "Roommate wanted", sublets "Sublet".
- **Penal Code 396** (`POST /checks/gouging`): the 160%-of-FMR rule is verified; the HUD FMR figures are still a
  third-party mirror marked unverified, so that path answers "unclear" until HUD's file is loaded.
- **Accounts.** Saving is local (localStorage) by default; optional Google sign-in syncs saves keyed by a salted hash of
  the Google subject (docs/ACCOUNTS.md). With sign-in off, `/auth/session` answers `{"enabled": false}`.
- **Pages added since the plan:** `/find`, `/saved`, `/alerts`, `/apartments/[id]`, `/gouging`, `/areas`,
  `/scenarios`, `/advisor`, `/privacy`, `/terms` (linked from the footer and `/about`).
- **Areas added on request** (`/areas` "Add this area"). `POST /areas/requests` queues a ZIP or city unless it is
  covered: core and county ZIPs, or a ZIP added on request within the last 30 days. A second request for a queued
  area returns the same request. `worker.ondemand` runs daily (13:30 UTC) within `ONDEMAND_DAILY_USD`: one batched
  Bright Data trigger, raw records, a replay into `staging_listings`, then tier `on_demand` and `last_scraped_at`.
  After 30 days a new request refreshes the area. Added and county ZIPs show their sampled listing count and median
  asking rent on `/zip/[zip]` (`AreaSummary.listings_sampled`, `median_asking_rent_usd`); the listing tracker itself
  stays on the 12 ZIPs.
