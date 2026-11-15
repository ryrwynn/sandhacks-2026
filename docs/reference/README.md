# Reference docs for the overnight run

Agents read the short notes in this folder instead of browsing vendor docs, which saves time and usage. `night-scout` writes them from two inputs: the raw docs you drop into `raw/` and public sources it researches.

## Drop raw docs here (not committed)

`docs/reference/raw/` is gitignored, because vendor docs are copyrighted and the repo is public. Each vendor folder already has a `public-docs-notes.md` summarizing the public docs; add account-specific facts beside it. Paste pages as `.md` or `.txt` (copy the page text, or use "Save as Markdown"), one file per page, in these folders:

| Folder | What to put in it |
| --- | --- |
| `raw/brightdata/` | Web Scraper API: trigger, progress, snapshot download, delivery options and limits. The Zillow scraper's page: inputs, `discover_by` options, output fields, price per 1,000 records. The Facebook "posts by group URL" scraper's page: inputs, output fields, price. Any Facebook group discovery or SERP API page you have access to. The dataset marketplace or filter API, if Zillow data can be bought by state. A text file `account.txt` with your remaining credit, your zones, and the dataset IDs you see in the dashboard. |
| `raw/tigerdata/` | Your service's plan and limits (storage, compute, connections) copied from the console. Docs pages on compression or columnstore, retention policies, continuous aggregates, pgvector / pgvectorscale / pgai, PostGIS, and forking a service. |
| `raw/mastra/` | The sponsor docs: getting started, agents, tools, workflows, memory, model providers (Gemini), running inside Next.js, and the MLH prize rules for Mastra. |
| `raw/gemini/` | Gemini API notes (models, limits, thinking, embeddings, errors). |
| `raw/google-auth/` | Only if you want Google sign-in: anything specific about your OAuth client. Put the keys themselves in `.env`, never here. |
| `raw/prizes/` | Judging criteria for the tracks you're targeting (Tiger Data, Bright Data, Mastra, Best Overall). |

## Notes night-scout writes

Each note is under 250 lines. It covers only what this project needs: endpoints, parameters, field names, limits, prices, and short code examples. It names its source file or URL and ends with a "Missing" section listing anything it couldn't find.

| Note | From |
| --- | --- |
| `brightdata.md` | `raw/brightdata/` plus Bright Data's public docs |
| `tigerdata.md` | `raw/tigerdata/` plus Tiger Data's public docs |
| `mastra.md` | `raw/mastra/` plus https://mastra.ai/docs |
| `gemini.md` | `raw/gemini/` plus aistudio.google.com/docs |
| `auth.md` | Auth.js docs (Google provider, `basePath`, JWT sessions) |
| `public-sources.md` | The research list below |

## Public sources night-scout researches

For each source, record its URL, publisher, license or terms, whether it needs a key, file size, update cadence, the fields we need, and why it can be trusted. Prefer government and first-party data publishers. Never use a source that needs a sign-in.

- **FRED** (Federal Reserve Bank of St. Louis): series IDs for San Diego MSA unemployment, US and West CPI shelter, the 30-year mortgage rate (MORTGAGE30US), and the San Diego house price index. Note the keyless CSV endpoint.
- **Federal Reserve supervisory scenarios** (federalreserve.gov): the latest baseline and severely adverse paths for unemployment, house prices, CPI and rates, as CSV.
- **Zillow Research**: ZORI and ZHVI for all California ZIPs; Zillow's home value and rent forecasts (ZHVF and the rent forecast, by ZIP or metro), with file URLs and column meanings.
- **Census**: ZCTA cartographic boundary files (500k), the ZCTA-to-county relationship file, and ACS 5-year variables already used (B19013_001E, B25064_001E) for all California ZCTAs in one call.
- **HUD**: Small Area Fair Market Rents for San Diego County ZIPs, and county FMRs for California, as downloadable files that need no token.
- **California law**: the current Penal Code 396 text (leginfo.legislature.ca.gov), the Attorney General's price-gouging guidance (oag.ca.gov), and the Governor's emergency proclamations and extensions that trigger it for any California county since 2025 (gov.ca.gov), with dates.
- **OpenStreetMap**: Overpass usage policy and polite limits; the Geofabrik California extract as the alternative for bulk amenity counts.
- **Libraries**: statsmodels SARIMAX with exogenous regressors and `get_forecast(...).conf_int`; conformal or empirical interval calibration for time series; pgvector usage from Python (psycopg); `next/font` font choices for cozy, readable themes (for example Nunito, Atkinson Hyperlegible, Fraunces, DM Sans); lucide-react icon names for tools and property types.
