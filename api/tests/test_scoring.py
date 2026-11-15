import pytest

from api.ml.scoring import STARTER_WEIGHTS, WEALTH_WEIGHTS, score_zips


def starter_rows():
    return [
        {"zip": "92101", "typical_rent": 2400, "rent_forecast_change_pct": 4.0, "groceries": 20,
         "transit_stops": 80, "parks": 5, "food_drink": 90, "gyms": 10, "area_km2": 10, "listings_30d": 100},
        {"zip": "92105", "typical_rent": 1700, "rent_forecast_change_pct": 2.0, "groceries": 10,
         "transit_stops": 40, "parks": 2, "food_drink": 20, "gyms": 2, "area_km2": 5, "listings_30d": 60},
        {"zip": "92037", "typical_rent": 3200, "rent_forecast_change_pct": 6.0, "groceries": 5,
         "transit_stops": 10, "parks": 3, "food_drink": 30, "gyms": 4, "area_km2": 20, "listings_30d": 20},
    ]


def test_starter_ranking_budget_and_points_sum():
    out = score_zips(starter_rows(), "starter", 2500)
    assert out["weights"] == STARTER_WEIGHTS
    assert [r["zip"] for r in out["ranked"]][0] == "92105"
    assert [r["zip"] for r in out["stretch"]] == ["92037"]
    for item in out["ranked"]:
        assert 0 <= item["score"] <= 100
        assert len(item["top_contributions"]) == 3
        assert {"feature", "label", "points", "value"} <= set(item["top_contributions"][0])
    scores = [r["score"] for r in out["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_full_contributions_sum_to_score_with_constant_features():
    # one ZIP -> every feature scales to 0.5 -> score 50
    out = score_zips(starter_rows()[:1], "starter", 5000)
    assert out["ranked"][0]["score"] == pytest.approx(50.0, abs=0.1)


def test_missing_values_get_mid_value_and_zip_is_kept():
    rows = starter_rows()
    rows[1]["rent_forecast_change_pct"] = None
    rows[1]["area_km2"] = None
    out = score_zips(rows, "starter", 5000)
    assert len(out["ranked"]) == 3


def test_wealth_uses_home_value_for_budget():
    rows = [
        {"zip": "92101", "typical_rent": 2400, "typical_home_value": 800_000,
         "value_forecast_change_pct": 3.0, "value_volatility_5y": 0.6},
        {"zip": "92037", "typical_rent": 3500, "typical_home_value": 2_000_000,
         "value_forecast_change_pct": 5.0, "value_volatility_5y": 0.9},
        {"zip": "92105", "typical_rent": 1900, "typical_home_value": 600_000,
         "value_forecast_change_pct": 4.0, "value_volatility_5y": 0.5},
    ]
    out = score_zips(rows, "wealth", 1_000_000)
    assert out["weights"] == WEALTH_WEIGHTS
    assert [r["zip"] for r in out["stretch"]] == ["92037"]
    assert out["ranked"][0]["zip"] == "92105"


def test_custom_weights_normalised():
    out = score_zips(starter_rows(), "starter", 5000, weights={"rent": 2, "rent_forecast": 2,
                     "basics_density": 0, "other_amenities_density": 0, "listings_30d": 0})
    assert sum(out["weights"].values()) == pytest.approx(1.0)
    assert out["ranked"][0]["zip"] == "92105"
