"""Every fixture in contracts/fixtures validates against its model in contracts/api_models.py."""
import json
from pathlib import Path

import pytest

from contracts import api_models as m

F = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
RESPONSES = {
    "health.json": m.HealthResponse, "zips.json": m.ZipsResponse, "zip_profile.json": m.ZipProfile,
    "zip_series_zori.json": m.SeriesResponse, "zip_series_zhvi.json": m.SeriesResponse,
    "check.json": m.CheckResponse, "letter.json": m.LetterResponse, "units_search.json": m.UnitSearchResponse,
    "listings_evaluate.json": m.ListingEvalResponse, "neighborhoods_rank_starter.json": m.RankResponse,
    "neighborhoods_rank_wealth.json": m.RankResponse, "owner_price_position.json": m.PricePositionResponse,
    "owner_listing_analysis.json": m.ListingAnalysisResponse,
    "listings.json": m.ListingsResponse, "listing_detail.json": m.ListingDetail,
    "listing_detail_facebook.json": m.ListingDetail, "market.json": m.MarketResponse,
    # overnight additions
    "zip_series_scenarios.json": m.SeriesResponse, "areas.json": m.AreasResponse,
    "area_request.json": m.AreaRequestStatus, "geo_zips.json": m.GeoZipsResponse,
    "zip_trends.json": m.ZipTrendsResponse, "listing_trends.json": m.ListingTrendsResponse,
    "gouging.json": m.GougingResponse, "match.json": m.MatchResponse, "owner_reach.json": m.OwnerReachResponse,
    "account_saves.json": m.AccountSavesResponse,
}
REQUESTS = {
    "checks.json": m.CheckRequest, "listings_evaluate.json": m.ListingEvalRequest,
    "neighborhoods_rank_starter.json": m.RankRequest, "neighborhoods_rank_wealth.json": m.RankRequest,
    "owner_price_position.json": m.PricePositionRequest, "owner_listing_analysis.json": m.ListingAnalysisRequest,
    "area_request.json": m.AreaRequestCreate, "gouging.json": m.GougingRequest, "match.json": m.MatchRequest,
    "owner_reach.json": m.OwnerReachRequest, "account_saves.json": m.PutSavesRequest,
}


@pytest.mark.parametrize("name,model", RESPONSES.items())
def test_response_fixture(name, model):
    model.model_validate(json.loads((F / name).read_text()))


@pytest.mark.parametrize("name,model", REQUESTS.items())
def test_request_fixture(name, model):
    model.model_validate(json.loads((F / "requests" / name).read_text()))


def test_demo_check_fixture_matches_plan():
    c = json.loads((F / "check.json").read_text())
    assert c["verdict"] == "over_cap" and c["max_legal_rent"] == 2272.20 and c["overage_monthly"] == 77.80
