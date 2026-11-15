"""AB 1482 rent-cap check (Civil Code 1947.12). Plain Python, no AI. Owner: lane B.

See docs/PLAN.md "Rent-cap detection logic" for the decision order and the required tests.
Decimal only; round down to the cent.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True)
class RentCap:
    region: str                        # 'san_diego_county'
    period_start: date
    period_end: date                   # inclusive
    cap_pct: Decimal                   # Decimal('8.20') means 8.2%
    source_url: str


@dataclass(frozen=True)
class CheckInput:
    lowest_rent_12mo: Decimal
    new_rent: Decimal
    effective_date: date
    year_built: int | None
    property_type: str                 # 'apartment' | 'condo' | 'single_family' | 'townhouse' | 'unknown'
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
    overage_yearly: Decimal | None = None
    increase_pct: Decimal | None = None   # (new - lowest) / lowest x 100, rounded down to 0.1
    third_increase: bool = False          # a third increase within 12 months
    figures: list[str] = field(default_factory=list)  # formatted figures Gemini may cite, e.g. '$2,272.20', '8.2%'


CENT = Decimal("0.01")
TENTH = Decimal("0.1")
HOMES = {"condo", "single_family", "townhouse"}
COVERAGE_YEARS = 15


def _money(x: Decimal) -> str:
    return f"${x:,.2f}"


def _pct(x: Decimal) -> str:
    return f"{x.normalize():f}%"


def _fmt_date(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def _result(verdict, reasons, cap=None, mx=None, over=None, over_y=None, pct=None, third=False, figures=None):
    return CheckResult(verdict, cap, mx, over, reasons, over_y, pct, third, figures or [])


def check_increase(inp: CheckInput, caps: list[RentCap]) -> CheckResult:
    pct = None
    if inp.lowest_rent_12mo > 0:
        pct = ((inp.new_rent - inp.lowest_rent_12mo) / inp.lowest_rent_12mo * 100).quantize(TENTH, ROUND_DOWN)
    third = inp.increases_last_12mo >= 2
    third_line = ("This would be a third rent increase within 12 months. The law allows at most two "
                  "increases in any 12 months, so this one may be unlawful no matter the amount.")

    def out(verdict, reasons, **kw):
        rs = list(reasons) + ([third_line] if third else [])
        figs = [_pct(pct)] if pct is not None and verdict in ("over_cap", "within_cap") else []
        return _result(verdict, rs, pct=pct, third=third, figures=kw.pop("figures", figs), **kw)

    # 1. Age exemption (year built stands in for the certificate of occupancy date)
    if inp.year_built is not None:
        age = inp.effective_date.year - inp.year_built
        if age < COVERAGE_YEARS - 1:
            return out("not_covered", [f"The building was built in {inp.year_built}, less than "
                       f"{COVERAGE_YEARS} years ago, so it is exempt from the AB 1482 rent cap."])
        if age <= COVERAGE_YEARS + 1:
            return out("unclear", [f"The building was built in {inp.year_built}, right around the "
                       f"{COVERAGE_YEARS}-year line. Buildings with a certificate of occupancy less than "
                       f"{COVERAGE_YEARS} years old are exempt, and the build year can differ from that date. "
                       "Ask the city or your landlord for the certificate date."])

    covered = []
    if inp.year_built is not None:
        covered.append(f"The building was built in {inp.year_built}, more than {COVERAGE_YEARS} years ago, "
                       "so AB 1482 covers it.")

    # 2. Single-family homes and condos
    if inp.property_type in HOMES:
        if inp.owner_is_corporate is True or inp.got_exemption_notice is False:
            covered.append("Homes and condos are exempt only when the owner is not a corporation or REIT and "
                           "you were given written notice of the exemption. That is not the case here, so the cap applies.")
        elif inp.got_exemption_notice is True and inp.owner_is_corporate is False:
            return out("not_covered", ["Your home is a condo or single-family house, the owner is not a "
                       "corporation, and you received the written exemption notice, so the cap does not apply."])
        else:
            return out("unclear", ["Condos and single-family homes are exempt only if the owner is not a "
                       "corporation or REIT and your lease says the property is not subject to the rent limits of "
                       "Civil Code 1947.12. We need both answers to say whether the cap applies."])

    # 3. Other exemptions
    if inp.other_exemption:
        return out("not_covered", ["You said the unit is exempt (the owner lives in the other half of a duplex, "
                   "it is a school dorm, or it is income-restricted affordable housing), so the cap does not apply."])

    # 4. Cap lookup
    row = next((c for c in caps if c.period_start <= inp.effective_date <= c.period_end), None)
    if row is None:
        return out("unclear", covered + [f"We don't have a rent cap on file for increases effective "
                   f"{_fmt_date(inp.effective_date)}, so we can't say whether the increase is allowed."])

    # 5. Compare
    cap = row.cap_pct
    mx = (inp.lowest_rent_12mo * (1 + cap / 100)).quantize(CENT, ROUND_DOWN)
    reasons = covered + [
        f"The cap for increases effective {_fmt_date(inp.effective_date)} in San Diego County is {_pct(cap)}.",
        f"Your lowest rent in the past 12 months was {_money(inp.lowest_rent_12mo)}, so the most your "
        f"landlord can charge is {_money(mx)}.",
    ]
    figs = [_money(inp.lowest_rent_12mo), _money(inp.new_rent), _pct(cap), _money(mx)]
    if pct is not None:
        figs.append(_pct(pct))
    if inp.new_rent > mx:
        over = inp.new_rent - mx
        over_y = over * 12
        reasons.append(f"The new rent of {_money(inp.new_rent)} is {_money(over)} a month over the limit "
                       f"({_money(over_y)} a year).")
        figs += [_money(over), _money(over_y)]
        verdict = "over_cap"
    else:
        over = over_y = None
        reasons.append(f"The new rent of {_money(inp.new_rent)} is within the limit.")
        verdict = "within_cap"
    if third:
        reasons.append(third_line)
    return _result(verdict, reasons, cap, mx, over, over_y, pct, third, figs)


def load_caps(conn) -> list[RentCap]:
    """Read rent_caps through a psycopg 3 connection."""
    with conn.cursor() as cur:
        cur.execute("SELECT region, period_start, period_end, cap_pct, source_url FROM rent_caps "
                    "ORDER BY region, period_start")
        return [RentCap(r[0], r[1], r[2], Decimal(r[3]), r[4]) for r in cur.fetchall()]
