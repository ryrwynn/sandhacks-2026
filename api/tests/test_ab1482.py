"""AB 1482 rule tests (docs/PLAN.md "Rent-cap detection logic")."""
from datetime import date
from decimal import Decimal as D

from api.rules.ab1482 import CheckInput, RentCap, check_increase

URL = "https://example.test/caps"
CAPS = [
    RentCap("san_diego_county", date(2025, 8, 1), date(2026, 7, 31), D("8.80"), URL),
    RentCap("san_diego_county", date(2026, 8, 1), date(2027, 7, 31), D("8.20"), URL),
]


def make(**kw) -> CheckInput:
    base = dict(
        lowest_rent_12mo=D("2100"), new_rent=D("2350"), effective_date=date(2026, 12, 1),
        year_built=1978, property_type="apartment", got_exemption_notice=None,
        owner_is_corporate=None, other_exemption=False, increases_last_12mo=0,
    )
    base.update(kw)
    return CheckInput(**base)


def test_demo_case():
    r = check_increase(make(), CAPS)
    assert r.verdict == "over_cap"
    assert r.cap_pct == D("8.2")
    assert r.max_legal_rent == D("2272.20")
    assert r.overage_monthly == D("77.80")
    assert r.overage_yearly == D("933.60")
    assert r.increase_pct == D("11.9")
    assert not r.third_increase
    assert "$2,272.20" in r.figures and "8.2%" in r.figures and "11.9%" in r.figures
    assert "$77.80" in r.figures and "$933.60" in r.figures
    assert all(isinstance(s, str) and s for s in r.reasons)


def test_exactly_at_cap_is_within():
    r = check_increase(make(new_rent=D("2272.20")), CAPS)
    assert r.verdict == "within_cap"
    assert r.overage_monthly in (None, D("0"), D("0.00"))


def test_one_cent_over_is_over():
    r = check_increase(make(new_rent=D("2272.21")), CAPS)
    assert r.verdict == "over_cap" and r.overage_monthly == D("0.01")


def test_rounds_down_to_cent():
    r = check_increase(make(lowest_rent_12mo=D("1999.99")), CAPS)
    assert r.max_legal_rent == D("2163.98")  # 2163.98918 rounded down


def test_2015_building_not_covered():
    r = check_increase(make(year_built=2015), CAPS)
    assert r.verdict == "not_covered" and r.reasons


def test_building_at_15_year_line_unclear():
    r = check_increase(make(year_built=2026 - 15), CAPS)
    assert r.verdict == "unclear"


def test_building_clearly_old_is_covered():
    assert check_increase(make(year_built=2000), CAPS).verdict == "over_cap"


def test_condo_with_notice_not_covered():
    r = check_increase(make(property_type="condo", got_exemption_notice=True, owner_is_corporate=False), CAPS)
    assert r.verdict == "not_covered"


def test_condo_without_notice_covered():
    r = check_increase(make(property_type="condo", got_exemption_notice=False, owner_is_corporate=False), CAPS)
    assert r.verdict == "over_cap"


def test_condo_corporate_owner_covered_even_with_notice():
    r = check_increase(make(property_type="condo", got_exemption_notice=True, owner_is_corporate=True), CAPS)
    assert r.verdict == "over_cap"


def test_condo_notice_unknown_unclear():
    r = check_increase(make(property_type="single_family", got_exemption_notice=None, owner_is_corporate=False), CAPS)
    assert r.verdict == "unclear"


def test_other_exemption():
    assert check_increase(make(other_exemption=True), CAPS).verdict == "not_covered"


def test_jul_31_uses_old_cap():
    r = check_increase(make(effective_date=date(2026, 7, 31)), CAPS)
    assert r.cap_pct == D("8.8") and r.max_legal_rent == D("2284.80")


def test_aug_1_uses_new_cap():
    r = check_increase(make(effective_date=date(2026, 8, 1)), CAPS)
    assert r.cap_pct == D("8.2") and r.max_legal_rent == D("2272.20")


def test_date_outside_caps_unclear():
    r = check_increase(make(effective_date=date(2028, 1, 1)), CAPS)
    assert r.verdict == "unclear" and r.reasons and r.max_legal_rent is None


def test_third_increase_flagged():
    r = check_increase(make(increases_last_12mo=2, new_rent=D("2200")), CAPS)
    assert r.verdict == "within_cap" and r.third_increase
    assert any("two" in s.lower() for s in r.reasons)


def test_second_increase_not_flagged():
    assert not check_increase(make(increases_last_12mo=1), CAPS).third_increase
