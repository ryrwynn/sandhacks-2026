# Public data sources: reference for RentOrKnot

Research on 2026-11-15 from the public pages named below. Nothing large was downloaded; only URLs and facts are recorded. "Verified" means a fetch or search returned the fact. "Unverified" means it is a guess from the URL pattern and must be checked before use. Blocked pages (403) are listed under Missing.

Trust rule (NIGHT.md): prefer government and first-party publishers. No source here needs a sign-in. Keys are never needed for the sources below; any optional key goes in `.env` and is read from the environment only.

User-Agent for every fetch: use a generic name such as `RentOrKnot-data/1.0` with no personal or project contact details.

## 1. FRED (Federal Reserve Bank of St. Louis)
- **Home:** https://fred.stlouisfed.org
- **Publisher:** Federal Reserve Bank of St. Louis (government). Data come from the original producers, named per series.
- **Terms:** FRED data are free for use; each series has its own copyright note. Cite the original source (for example Freddie Mac for MORTGAGE30US).
- **Key:** Keyless CSV endpoint (standard FRED pattern; the series pages were checked, the CSV URL itself was not fetched): `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>`. The JSON API (`api.stlouisfed.org`) needs a free key; use only if the CSV route fails.
- **Series we need (verified on the series page):**
  | Series ID | Title | Units / frequency | Source | Latest seen |
  | --- | --- | --- | --- | --- |
  | `CASAND5URN` | San Diego County unemployment rate | Percent, monthly, not seasonally adjusted | BLS (via FRED) | Sep 2026: 4.7%; next release Dec 2, 2026 |
  | `SDXRSA` | Case-Shiller CA-San Diego Home Price Index (house price index) | Index Jan 2000 = 100, seasonally adjusted, monthly | S&P Dow Jones Indices (via FRED) | Aug 2026: 446.87 |
  | `MORTGAGE30US` | 30-year fixed mortgage average, US | Percent, weekly (Thursday), not seasonally adjusted | Freddie Mac PMMS | 2026-11-12: 7.11% |
  - Other series NIGHT.md names (US and West CPI shelter): series IDs UNVERIFIED (see Missing).
- **Size:** each series CSV is a few KB (not measured; estimate only).
- **Cadence:** monthly series update monthly; MORTGAGE30US weekly; SDXRSA last updated Oct 27, 2026 for Aug 2026 data.
- **Fields in the CSV:** `observation_date` (or `DATE`) and the series ID column.
- **Why trusted:** Federal Reserve Bank publication that mirrors BLS, S&P and Freddie Mac data with their citations.

## 2. Federal Reserve supervisory stress-test scenarios (federalreserve.gov)
- **Home:** https://www.federalreserve.gov/publications/2026-stress-test-scenarios.htm
- **Publisher:** Board of Governors of the Federal Reserve System (government).
- **Documents found (verified in search):**
  - Final 2026 scenarios, Feb 4, 2026: https://www.federalreserve.gov/publications/files/2026-final-supervisory-stress-test-scenarios-20260204.pdf
  - Final macroeconomic model guide: https://www.federalreserve.gov/supervisionreg/files/2026-final-macroeconomic-model-guide.pdf
  - 2026 DFAST results (June 24, 2026): https://www.federalreserve.gov/publications/files/2026-dfast-results-20260624.pdf
- **Key facts (from the scenario document summary):** the 2026 severely adverse scenario has unemployment rising to **10%**, real GDP falling **4.6%** peak to trough, house prices down **30%**, and CRE prices down 39%.
- **Terms:** public government documents; no restriction found.
- **Key:** none. Files are PDF; **a CSV of the scenario paths was NOT found** (see Missing).
- **Cadence:** annual (proposed in October, final in February, results in June).
- **Fields we need:** quarterly paths for unemployment, house prices, CPI and the 3-month and 10-year rates; baseline and severely adverse. The PDF tables give these; transcribe into a CSV by hand in `data/` if no CSV exists.
- **Why trusted:** official Fed publication, the source of the supervisory scenarios.

## 3. Zillow Research (ZORI, ZHVI, forecasts)
- **Home:** https://www.zillow.com/research/data/
- **Publisher:** Zillow Group (private company, first-party data publisher for its own indexes).
- **Terms:** UNVERIFIED. The Zillow data page returned 403 to fetching, so the license text was NOT read. Assume attribution is required.
- **Key:** none.
- **Indexes:** ZORI (Observed Rent Index, smoothed market-rate rent, calculated at national, metro, county, city and ZIP levels where data are sufficient) and ZHVI (home value index). Home value forecast (ZHVF) and rent forecast files are on the same page (names UNVERIFIED).
- **Cadence:** monthly; data posted around the 16th of each month (per a Zillow data page via search).
- **Size:** ZIP-level files are large (tens of MB for all US ZIPs). **Do not download the national file.** Use a California-only extract, or the state-level file, and record the URL.
- **Fields:** `RegionID`, `SizeRank`, `RegionName` (ZIP), `RegionType`, `StateName`, `State`, `City`, `Metro`, `CountyName`, then one column per month date.
- **Caveat:** some ZIP codes in the Region Name column are not five digits and are unreliable; check the ZIP length before joining.
- **Why trusted:** Zillow publishes its own methodology pages for each index; used in this project as the index tier source.

## 4. Census Bureau (ZCTA boundaries, relationship file, ACS)
- **Home:** https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html
- **Publisher:** US Census Bureau (government).
- **Terms:** public domain (US government work).
- **Key:** none for file downloads. The ACS API accepts requests without a key for small calls; a key is optional (UNVERIFIED for our call volume).
- **ZCTA cartographic boundary file, 500k scale:** the 2024 national file is expected at `https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_zcta520_500k.zip` (**UNVERIFIED**; the directory listing did not show it and the search only confirmed the GENZ2024 pattern for state files). The 2020 version is `cb_2020_us_zcta520_500k.zip` (confirmed name in search results). The `tigris` R package also fetches it.
- **ZCTA-to-county relationship file:** not found on the directory page read (**Missing**).
- **ACS 5-year variables (from NIGHT.md):** `B19013_001E` (median household income) and `B25064_001E` (median gross rent), for all California ZCTAs in one API call (`for=zip%20code%20tabulation%20area:*&in=state:06`). Endpoint pattern UNVERIFIED for the current release year.
- **Cadence:** ACS 5-year estimates yearly; cartographic files yearly (boundary vintage changes after each decennial census).
- **Size:** the 500k ZCTA shapefile is tens of MB; split and simplify before serving (see NIGHT.md map geometry).
- **Why trusted:** the official statistical agency for the US.

## 5. HUD (Fair Market Rents, Small Area FMRs)
- **Home:** https://www.huduser.gov/portal/datasets/fmr.html and the Small Area FMR page https://www.huduser.gov/portal/datasets/fmr/smallarea/index.html
- **Publisher:** US Department of Housing and Urban Development (government).
- **Terms:** public government data; no restriction found on the page (fetch returned empty; the terms were NOT read).
- **Key:** NIGHT.md says no token is needed for the downloadable files. Not verified on the page read.
- **FY2026 metro FMRs (40th percentile, third-party mirror of HUD data):** San Diego-Chula Vista-Carlsbad studio $2,288; 1BR $2,459; 2BR $3,001; 3BR $3,998; 4BR $4,845. FY2026 FMRs took effect Oct 1, 2025.
- **ZIP-level SAFMRs (third-party only, UNVERIFIED against HUD):** 2BR $4,280 for ZIP 92011 and $4,200 for ZIP 92075.
- **Fields:** SAFMR files list ZIP, metro, and FMR per bedroom count (`Metro_Name`, `ZIP`, `SAFMR_0BR`... `SAFMR_4BR` in the usual layout; UNVERIFIED for the current file).
- **Cadence:** annual, effective each Oct 1 (one mid-year update in May 2026 for some areas per a policy site; San Diego not confirmed).
- **Why trusted:** HUD sets these numbers; the third-party figures agree with each other, but verify against the HUD file.

## 6. California law (Penal Code 396, Attorney General, Governor's proclamations)
- **Statute:** https://leginfo.legislature.ca.gov (Penal Code section 396). **The fetch returned 403**; text below comes from secondary summaries and must be checked on the official page.
- **Publisher:** California Legislature (government).
- **Terms:** public law.
- **Key:** none.
- **Rule (secondary sources):** during a declared state of emergency, prices may not rise more than **10%** over the pre-emergency price. Contractors may charge no more than 10% above their pre-emergency price for repair or emergency services. If no price was charged before the emergency, a seller may not charge more than **50%** above a benchmark (wording not fully verified). Violation is a misdemeanor (up to 1 year and/or $10,000).
- **Trigger:** a declaration by the President, the Governor, or a local government.
- **Cal OES:** https://caloes.ca.gov/cal-oes-divisions/legal-affairs/price-gouging (summary page, not fetched).
- **AG guidance:** oag.ca.gov (not fetched; URL from NIGHT.md).
- **Governor's proclamations:** gov.ca.gov (not fetched; the list for 2025 and 2026 counties is **Missing**).
- **Why trusted:** the statute itself is the authority; the Cal OES and AG pages are the state's own guidance.

## 7. OpenStreetMap (Overpass and Geofabrik)
- **Home:** https://operations.osmfoundation.org/policies/api/ (usage policy, fetched).
- **Publisher:** OpenStreetMap Foundation (non-profit); the Overpass API is run by volunteers and hosts.
- **Terms:** Open Database License (ODbL); attribution required ("© OpenStreetMap contributors").
- **Key:** none.
- **Limits (verified on the policy page):**
  - No numeric rate limit stated; **maximum of 2 download threads**.
  - A valid User-Agent identifying the application is required; spoofing another app's User-Agent gets you blocked.
  - Large or frequent bulk users should use planet files or their own data server; access may be blocked without notice.
- **Geofabrik** (California extract, the alternative for bulk amenity counts; URL from NIGHT.md, not fetched): one file per region, updated daily. Size of the California extract UNVERIFIED (estimate: a few hundred MB as PBF).
- **Fields we need:** `amenity`, `shop`, `public_transport`, `leisure` tags within a ZIP's bounding box.
- **Why trusted:** community-maintained open data with a published policy and a named foundation; use attribution.

## 8. Libraries (not researched tonight)
NIGHT.md lists these for the forecast, match and theme lanes. They were **not researched** in this run to save budget:
- statsmodels SARIMAX with exogenous regressors and `get_forecast(...).conf_int` (already installed on the server per NIGHT.md)
- conformal or empirical interval calibration for time series
- pgvector from Python (psycopg)
- `next/font` choices (Nunito, Atkinson Hyperlegible, Fraunces, DM Sans)
- lucide-react icon names for tools and property types

Fallback: use the installed libraries and the documented APIs in each lane; check icon names against the installed lucide-react package.

## Missing
- **FRED CPI shelter series IDs** (US and West): not looked up. Fallback: use `CUSR0000SAH1` (US shelter) and `CUUR0400SAH1` (West shelter) only after checking them on FRED; if not found, use the San Diego house price index and the mortgage rate only.
- **Fed scenario data as CSV:** only PDFs found. Fallback: transcribe the quarterly paths from the PDF tables into `data/fed_scenarios.csv` with a source note.
- **Zillow direct file URLs** (ZORI, ZHVI, forecasts): the Zillow data page returned 403, and search did not give the exact paths. Fallback: use the Zillow data page's links at build time, and store the URL used in `sources/*.yaml`; skip the forecast file if not found.
- **Zillow license text:** the page was not readable. Fallback: attribute "Zillow Research" in the UI and the README, and do not redistribute raw files.
- **ZCTA 2024 500k shapefile URL and ZCTA-to-county relationship file:** the 2024 ZCTA name is unverified and the relationship file was not on the page. Fallback: use the 2020 `cb_2020_us_zcta520_500k.zip` (confirmed name) and derive county membership from the county boundary file or Census relationship file from the same directory if found.
- **ACS API endpoint for the current release year and key rules:** Fallback: use the 5-year release one year back (confirm on the Census API page) and read a key from the environment if the call is refused.
- **HUD SAFMR file URLs and columns, and token rules:** the HUD page returned empty. Fallback: use the FY2026 metro FMR figures above (third-party mirror) and mark ZIP-level SAFMRs as unverified until the HUD file is read.
- **Penal Code 396 official text:** leginfo returned 403. Fallback: encode the 10% rule with the statute citation and a "verify on leginfo" note in the rules code and the UI footnote.
- **Governor's emergency proclamations for 2025 to 2026:** not searched. Fallback: store proclamation dates in a YAML table with the URL of each gov.ca.gov page, and mark the table as manually maintained.
- **Geofabrik California extract size and update time:** not fetched. Fallback: use the Overpass API with polite limits (2 threads, valid User-Agent) for the on-demand areas.
- **Library facts** (section 8 above): not researched. Fallback: use the installed versions and each library's own docs at build time.
