from api.ml.listing_analysis import FACTS, analyze_listing, percentile_of, readability

FULL = ("Sunny 2 bedroom, 1 bath, 850 sq ft. $2,400/mo. Pets welcome. Garage parking. "
        "Washer and dryer in unit. Water and trash included. Available Dec 1.")
THIN = "Nice 2 bedroom apartment for $2,400 a month. Close to shops."


def test_percentile_of():
    assert percentile_of(2000, [1000, 1500, 2500, 3000]) == 50.0
    assert percentile_of(2000, []) is None


def test_full_listing_states_everything():
    r = analyze_listing(FULL, [])
    assert r["completeness"] == 100.0
    assert all(r["stated"][f] for f in FACTS)
    assert r["gaps"] == []


def test_gaps_against_comparables():
    r = analyze_listing(THIN, [FULL] * 4 + [THIN])
    assert r["stated"]["price"] and r["stated"]["beds"] and not r["stated"]["parking"]
    gaps = {g["fact"]: g["share_of_comparables"] for g in r["gaps"]}
    assert gaps["parking"] == 0.8 and gaps["laundry"] == 0.8
    assert "price" not in gaps
    shares = [g["share_of_comparables"] for g in r["gaps"]]
    assert shares == sorted(shares, reverse=True)


def test_reach_depends_on_price_position():
    cheap = analyze_listing(THIN, [], price_percentile=10)["reach_score"]
    pricey = analyze_listing(THIN, [], price_percentile=95)["reach_score"]
    assert cheap > pricey
    assert 0 <= pricey <= cheap <= 100


def test_readability_bounds():
    assert 0 <= readability(FULL) <= 100
    assert readability("") == 0.0
    assert readability("The cat sat. The dog ran.") > readability(
        "Notwithstanding aforementioned contractual considerations, prospective occupants "
        "must demonstrate comprehensive financial documentation.")
