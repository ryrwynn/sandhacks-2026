# Fixtures

One JSON response per endpoint (`*.json`) and one request body per POST endpoint (`requests/`),
generated from `contracts/api_models.py` and checked by `api/tests/test_contracts.py`.
They are sample shapes for mocks and tests only: never load them into the database, and never
show their numbers as real data. `sources/<key>/` holds raw source samples for the adapter golden tests.

| Endpoint | Response fixture | Request fixture |
| --- | --- | --- |
| GET /health | health.json | |
| GET /zips | zips.json | |
| GET /zips/{zip} | zip_profile.json | |
| GET /zips/{zip}/series?metric=zori\|zhvi | zip_series_zori.json, zip_series_zhvi.json | |
| POST /checks | check.json | requests/checks.json (the plan's demo case) |
| POST /checks/{id}/letter?lang=es | letter.json | |
| GET /units/search?address= | units_search.json | |
| POST /listings/evaluate | listings_evaluate.json | requests/listings_evaluate.json |
| POST /neighborhoods/rank | neighborhoods_rank_starter.json, neighborhoods_rank_wealth.json | requests/neighborhoods_rank_*.json |
| POST /owner/price-position | owner_price_position.json | requests/owner_price_position.json |
| POST /owner/listing-analysis | owner_listing_analysis.json | requests/owner_listing_analysis.json |
| GET /listings?zip=&beds=&type=&max_price=&sort=&limit=&offset= and ?ids= (up to 50) | listings.json | |
| GET /listings/{id} | listing_detail.json | |
| GET /market?zip=&beds=&type=&range= | market.json | |

The tracker fixtures are sample shapes: their numbers are illustrative, never real data. Price history in the real
endpoints comes only from stored price_observations (the source's own history events plus each scrape's sightings);
a month with no observation has no point.
