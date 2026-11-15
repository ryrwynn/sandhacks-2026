# RentOrKnot forecast model card

Scenario forecasts of ZORI (typical rent) and ZHVI (typical home value) for the 12 covered San Diego ZIPs, 12 months ahead, with an 80% range. Added overnight by the night-forecast lane. The default `/zips/{zip}/series` response is unchanged; scenarios appear only with `?scenario=baseline|recession|growth`.

**Not financial advice.** These are statistical projections from public indexes. Recession and growth are what-if cases, not predictions.

## Data

- ZORI and ZHVI per ZIP: Zillow Research public CSVs (committed extracts `data/zillow_zori_sd.csv` for 2017-05 to 2026-09 and `data/zillow_zhvi_sd.csv` for 2000-01 to 2026-09), 12 ZIPs.
- Macro inputs from FRED (keyless CSV): `CASAND5URN` San Diego County unemployment (BLS), `SDXRSA` Case-Shiller San Diego home price index (S&P), `MORTGAGE30US` 30-year mortgage rate (Freddie Mac, weekly, averaged by month), plus `CUSR0000SAH1` US CPI shelter (verified to exist; stored for context, not used as a regressor). Monthly snapshot: `api/ml/data/macro_monthly.csv` (323 months, from 2000).
- Fed scenario paths: **entered by hand**, because the Federal Reserve published them only as a PDF. Source: Board of Governors, "2026 Stress Test Scenarios" (final, Feb 4 2026), Table 3.A (supervisory baseline, PDF page 35) and Table 4.A (supervisory severely adverse, PDF page 36). Unemployment, mortgage rate and house price index, Q1 2026 to Q1 2029, in `sources/macro_scenarios.yaml` with the URL. These are national paths for a hypothetical stress test.
- Late-published macro months (house prices lag by about two months) are carried forward from the last published value.

## Scenarios

A scenario is a path of changes over the next 12 months, applied to the latest actual San Diego values:

| Scenario | Source of the path |
|---|---|
| baseline | Fed 2026 supervisory baseline shape: unemployment drifts down about 0.3 points, mortgage rates ease, house prices about flat |
| recession | Fed 2026 severely adverse shape, taken from the Fed baseline's own Q1 2026 jump-off as if the shock starts at the forecast origin: unemployment up about 5 points toward 10%, house prices down about 25% within a year |
| growth | Not from the Fed. A documented upside derived from San Diego history: the 20th percentile (unemployment and mortgage rate) and 80th percentile (house prices) of historical 12-month changes since 2000, ramped linearly over 12 months |

Using the Fed paths as shapes rather than levels is a modelling choice: the Fed paths start from a national jump-off, not from today's San Diego values.

## Method

- Pooled direct ridge regression over ZIPs, one model per horizon h = 1..12 (statsmodels and scikit-learn only; no new dependency): the h-month log change of ZORI or ZHVI against the ZIP's 1-, 3- and 12-month momentum plus the change over those h months in unemployment (points), log house price index and mortgage rate (points). Training uses realized macro changes; forecasting uses the scenario path. Ridge alpha 30, standardized features. Code: `api/ml/scenario_model.py`.
- Benchmarks: naive (last value held) and the existing ETS (damped additive trend on log values, `api/ml/forecast.py`).
- Rolling-origin backtest: origins every 3 months starting at month 60, each fit on data up to the origin only. MAPE is the mean over origins and horizons 1..12. The first 5 origins only seed the cone; the rest are scored ("test origins").
- 80% cone: rolling conformal. At each origin the band is the 10th to 90th percentile of past pooled errors at each horizon, multiplied by a factor set so that recent, fully observed outcomes (up to 32 origins) were covered 80% of the time. It uses only errors already observed at that origin, so the coverage below is out of sample. Scenario cones reuse the baseline residual band around the scenario's own mean. The ETS cone is statsmodels' own 80% interval.
- Baseline backtest assumes macro held flat at the origin (close to the Fed baseline shape). Recession and growth rows apply those scenario paths at every past origin and score them against what actually happened, so they are expected to be poor: the world did not follow them. "Oracle" feeds the model the realized macro path, which tests whether the macro regressors carry signal.
- Model choice: per metric, the baseline is served from whichever of the pooled model and ETS had the lower mean test MAPE (selected on the same backtest, so slightly optimistic). Recession and growth always use the pooled model, the only one that takes macro paths.

## Backtest results

MAPE in percent, 80% coverage as a share. Held-out test origins: 9 for ZORI (short history), 78 for ZHVI.

### Summary (mean across the 12 ZIPs)

| Series | naive | ETS | baseline | recession | growth | oracle | baseline cov | ETS cov | recession cov | growth cov |
|---|---|---|---|---|---|---|---|---|---|---|
| ZORI | 1.27 | 1.73 | 1.63 | 4.63 | 2.96 | 1.68 | 0.92 | 0.95 | 0.24 | 0.85 |
| ZHVI | 4.56 | 3.04 | 3.30 | 8.06 | 4.68 | 2.05 | 0.75 | 0.79 | 0.24 | 0.69 |

### What improved

- ZORI: the macro model beats ETS (1.63 vs 1.73 MAPE; baseline is lower in 9 of 12 ZIPs) but does **not** beat naive (1.27). Rents move slowly and the naive "no change" forecast is hard to beat over 9 test origins. We do not claim a gain over naive for rents.
- ZHVI: the macro model beats naive (3.30 vs 4.56) but **not** ETS (3.04), so ETS stays the served baseline for home values. The oracle result (2.05) shows the macro regressors have real signal when the macro path is known, which is what the scenario toggle uses them for.
- Not compared with Zillow's own published forecasts: those files were not fetched tonight, so no claim is made against them.
- Coverage: ZHVI baseline 0.75 and ZORI baseline 0.92 are the calibrated cone's held-out numbers. ZHVI is a little under 0.80 (the rolling factor lags regime changes); ZORI is over 0.80 on only 9 origins, so it is noisy. ETS's own interval is closer to 0.80 for ZHVI (0.79) and too wide for ZORI (0.95).
- Decision (morning run, 2026-11-15): the ZHVI cone is **not** widened. Instead each ZIP page's "Typical home value"
  and "Typical rent" charts print the measured held-out coverage of the served baseline from the latest training
  (`coverage_80` of `/zips/{zip}/series?scenario=baseline`), and add "the target is 80%, so treat it as a little
  narrow" when it is below 80%. Widening needs a retrain against the database; revisit if a rerun stays under 0.78.
- Recession and growth coverage against actual outcomes is low by construction (the scenarios did not happen). Do not read it as miscalibration.

Per-ZIP tables (MAPE %, then coverage; the last row is the all-ZIP mean):

#### ZORI per ZIP (held-out origins; MAPE %, then 80% coverage)

| ZIP | naive | ETS | baseline | recession | growth | oracle | baseline cov | ETS cov | recession cov | growth cov |
|---|---|---|---|---|---|---|---|---|---|---|
| 91910 | 1.04 | 0.67 | 1.11 | 4.91 | 2.58 | 1.03 | 0.96 | 0.99 | 0.23 | 0.92 |
| 92126 | 1.19 | 1.87 | 1.72 | 4.38 | 3.14 | 1.78 | 0.94 | 0.99 | 0.27 | 0.86 |
| 92105 | 1.11 | 1.41 | 1.41 | 4.86 | 2.69 | 1.53 | 0.95 | 0.94 | 0.23 | 0.87 |
| 92101 | 0.76 | 1.26 | 1.77 | 4.18 | 3.36 | 1.72 | 0.91 | 0.96 | 0.19 | 0.88 |
| 92117 | 1.21 | 1.84 | 1.70 | 4.61 | 3.04 | 1.81 | 0.91 | 0.90 | 0.26 | 0.79 |
| 92104 | 1.05 | 1.80 | 1.65 | 4.55 | 2.99 | 1.80 | 0.93 | 0.93 | 0.29 | 0.79 |
| 92122 | 1.44 | 2.39 | 2.20 | 4.26 | 3.59 | 2.15 | 0.87 | 0.95 | 0.26 | 0.88 |
| 92111 | 1.65 | 2.00 | 1.60 | 4.83 | 2.71 | 1.57 | 0.91 | 0.92 | 0.20 | 0.79 |
| 92109 | 1.71 | 1.55 | 1.41 | 5.00 | 2.54 | 1.53 | 0.87 | 0.97 | 0.20 | 0.91 |
| 92103 | 1.06 | 1.65 | 1.43 | 4.63 | 2.86 | 1.42 | 0.96 | 1.00 | 0.19 | 0.86 |
| 92107 | 1.76 | 2.59 | 1.50 | 5.35 | 2.37 | 1.73 | 0.91 | 0.90 | 0.21 | 0.92 |
| 92108 | 1.19 | 1.78 | 2.09 | 4.00 | 3.59 | 2.06 | 0.93 | 1.00 | 0.29 | 0.80 |
| **all** | 1.265 | 1.733 | 1.632 | 4.629 | 2.955 | 1.678 | 0.92 | 0.954 | 0.235 | 0.853 |

Test origins: 9. Baseline served from: pooled_x.

#### ZHVI per ZIP (held-out origins; MAPE %, then 80% coverage)

| ZIP | naive | ETS | baseline | recession | growth | oracle | baseline cov | ETS cov | recession cov | growth cov |
|---|---|---|---|---|---|---|---|---|---|---|
| 91910 | 5.15 | 3.16 | 3.58 | 8.35 | 4.92 | 2.00 | 0.74 | 0.77 | 0.24 | 0.71 |
| 92126 | 4.96 | 3.23 | 3.58 | 8.30 | 4.59 | 2.01 | 0.71 | 0.74 | 0.24 | 0.70 |
| 92105 | 5.86 | 3.55 | 4.09 | 8.73 | 4.97 | 2.49 | 0.70 | 0.72 | 0.22 | 0.67 |
| 92101 | 3.86 | 2.42 | 2.74 | 7.29 | 5.08 | 2.12 | 0.81 | 0.84 | 0.28 | 0.66 |
| 92117 | 4.65 | 3.27 | 3.42 | 8.07 | 4.52 | 2.11 | 0.73 | 0.74 | 0.26 | 0.69 |
| 92104 | 4.64 | 3.30 | 3.50 | 8.12 | 4.82 | 2.42 | 0.73 | 0.85 | 0.25 | 0.65 |
| 92122 | 4.22 | 2.92 | 3.06 | 8.10 | 4.40 | 1.78 | 0.79 | 0.82 | 0.23 | 0.74 |
| 92111 | 4.75 | 3.18 | 3.48 | 8.21 | 4.46 | 2.04 | 0.73 | 0.75 | 0.24 | 0.69 |
| 92109 | 4.11 | 3.02 | 3.04 | 8.09 | 4.33 | 1.91 | 0.78 | 0.75 | 0.21 | 0.71 |
| 92103 | 3.73 | 2.80 | 2.85 | 7.69 | 4.67 | 1.88 | 0.77 | 0.89 | 0.27 | 0.70 |
| 92107 | 3.93 | 2.73 | 2.86 | 8.04 | 4.35 | 1.80 | 0.78 | 0.84 | 0.22 | 0.71 |
| 92108 | 4.84 | 2.92 | 3.42 | 7.75 | 5.03 | 2.08 | 0.76 | 0.76 | 0.26 | 0.66 |
| **all** | 4.558 | 3.042 | 3.301 | 8.062 | 4.677 | 2.053 | 0.75 | 0.789 | 0.244 | 0.692 |

Test origins: 78. Baseline served from: ets.


## Limits

- ZORI history starts in 2017, so the ZORI backtest has few origins and no recession of its own; ZHVI includes 2008.
- Twelve ZIPs share one San Diego macro series, so the macro coefficients are estimated from about 25 years (ZHVI) or 9 years (ZORI) of one time series, not from independent ZIPs.
- The Fed paths are national stress-test paths, the recession path is extreme (about 25% house price fall), and rent responds to it only through the fitted relationship, which is estimated mostly from mild and boom periods. Treat the recession cone as a stress illustration.
- Scenario rows are written for the 12 core ZIPs only; other tiers stay out of the shared database.
- Zillow indexes smooth rents and are not asking rents on any given listing.

## Reproduce

```
uv run python -m worker.macro snapshot        # refresh api/ml/data/macro_monthly.csv from FRED
uv run python -m api.ml.scenario_run          # print the tables above from the committed extracts
DATABASE_URL=... uv run python -m worker.macro load        # macro_series and scenario_paths
DATABASE_URL=... uv run python -m worker.train scenarios   # scenario_forecasts, core ZIPs only
```

Trends (`/zips/{zip}/trends`, `/listings/{id}/trends`) are descriptive market signals computed from the same indexes and from listing price history. They are not legal findings and not financial advice.
