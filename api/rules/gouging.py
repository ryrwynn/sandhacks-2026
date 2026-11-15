"""California Penal Code 396 rent-gouging check (night-rules). Sits beside ab1482.py and never replaces it.

Data: api/rules/data/emergencies.yaml (declarations, extensions, counties, source URLs, dates), fmr.yaml (HUD Fair
Market Rents) and zip_county.yaml. Money in Decimal, rounded down to the cent.
"""
from datetime import date
from decimal import ROUND_DOWN, Decimal
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

import yaml

DATA = Path(__file__).parent / "data"
CENT = Decimal("0.01")


class GougingResult(TypedDict):
    verdict: str                     # 'likely_violation' | 'within_limit' | 'not_covered' | 'unclear'
    county: str | None
    limit_usd: Decimal | None
    increase_pct: Decimal | None
    basis: str                       # 'pre_emergency_plus_10' | 'fmr_160' | 'none'
    fmr_usd: Decimal | None
    fmr_source: str | None
    emergency: dict | None           # keys of contracts.api_models.EmergencyInfo
    reasons: list[str]
    unverified: list[str]            # inputs not yet checked against their official source


def _yaml(name: str) -> dict:
    return yaml.safe_load((DATA / name).read_text())


@lru_cache
def load_emergencies() -> list[dict]:
    return _yaml("emergencies.yaml")["declarations"]


@lru_cache
def load_fmr() -> dict:
    d = _yaml("fmr.yaml")
    for table in (d["county_fmr"], d.get("safmr") or {}):
        for e in table.values():
            e["rents"] = {int(k): Decimal(str(v)) for k, v in e["rents"].items()}
    return d


@lru_cache
def load_zip_county() -> dict[str, str]:
    out: dict[str, str] = {}
    for county, v in _yaml("zip_county.yaml")["counties"].items():
        for lo, hi in v["ranges"]:
            out.update({str(z): county for z in range(lo, hi + 1)})
    return out


def _down(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_DOWN)


def _money(x: Decimal) -> str:
    return f"${x:,.2f}"


def _canon_county(name: str, known: set[str]) -> str:
    n = name.strip().lower().removesuffix(" county").strip()
    return next((k for k in known if k.lower() == n), name.strip().title())


FMR_RULE_UNVERIFIED = "the 160%-of-Fair-Market-Rent rule (statute text not yet checked)"
FMR_RULE_VERIFIED = True       # Penal Code 396(e): 160% of HUD Fair Market Rent; owner verified the statute 2026-11-15


def _result(verdict, county, reasons, *, limit=None, pct=None, basis="none", fmr=None, fmr_source=None, em=None,
            unverified=None):
    """`unverified` names each input the answer rests on that hasn't been checked against its official source."""
    unv = list(unverified or [])
    if basis == "fmr_160" and not FMR_RULE_VERIFIED and FMR_RULE_UNVERIFIED not in unv:
        unv.append(FMR_RULE_UNVERIFIED)
    if unv and verdict in ("likely_violation", "within_limit"):   # never a firm answer on unchecked data
        reasons = list(reasons) + [f"Because {' and '.join(unv)} {'is' if len(unv) == 1 else 'are'} not verified "
                                   "yet, we can't give a firm answer."]
        verdict = "unclear"
    return GougingResult(verdict=verdict, county=county, limit_usd=limit, increase_pct=pct, basis=basis,
                         fmr_usd=fmr, fmr_source=fmr_source, emergency=em, reasons=reasons, unverified=unv)


def check_gouging(new_rent: Decimal, offer_date: date, *, zip_: str | None = None, county: str | None = None,
                  pre_emergency_rent: Decimal | None = None, beds: int | None = None) -> GougingResult:
    emergencies = load_emergencies()
    zips = load_zip_county()
    known = {c for e in emergencies for c in e["counties"]} | set(zips.values())
    z = (zip_ or "").strip()
    if county and county.strip():
        county = _canon_county(county, known)
    elif z in zips:
        county = zips[z]
    else:
        county = None
    if county is None:
        return _result("unclear", None, ["We could not tell which county this unit is in, so we can't say whether "
                                         "an emergency applies. Enter a San Diego County ZIP or pick a county."])

    in_county = [e for e in emergencies if county in e["counties"] and e.get("declared_on")]
    if not in_county:
        return _result("not_covered", county, [
            f"We found no state of emergency covering {county} County in our list, so the Penal Code 396 limit "
            "doesn't apply. Local emergencies are not included; check with the county or city."])
    rental = [e for e in in_county if e.get("rental_covered")]
    active = [e for e in rental if e["declared_on"] <= offer_date <= e["protections_until"]]
    if not active:
        if not rental:
            why = "the emergency on our list doesn't cover rental housing"
        else:
            e = rental[0]
            why = (f"{e['title']} was declared on {e['declared_on']:%B %d, %Y} and rent protections run through "
                   f"{e['protections_until']:%B %d, %Y}; {offer_date:%B %d, %Y} is outside that window")
        return _result("not_covered", county, [
            f"The Penal Code 396 limit applies only during a declared emergency, and {why}. "
            "Your rent could still be limited by AB 1482 or local rules."])
    e = active[0]
    em = {"title": e["title"], "counties": list(e["counties"]), "declared_on": e["declared_on"],
          "protections_until": e["protections_until"], "extensions": list(e.get("extensions") or []),
          "source_url": e["source_url"]}
    inside = (f"{e['title']} was declared on {e['declared_on']:%B %d, %Y}; protections run through "
              f"{e['protections_until']:%B %d, %Y}.")
    unv = []
    if not e.get("verified", False):
        inside += " This declaration has not been fully verified against the official proclamation."
        unv.append("the emergency declaration")

    if pre_emergency_rent is not None:
        limit = _down(pre_emergency_rent * Decimal("1.10"))
        pct = ((new_rent - pre_emergency_rent) / pre_emergency_rent * 100).quantize(CENT, rounding=ROUND_DOWN)
        over = new_rent > limit
        reasons = [inside,
                   f"The rent went from {_money(pre_emergency_rent)} to {_money(new_rent)}, an increase of about "
                   f"{pct}%. The limit is 10% over the pre-emergency rent, {_money(limit)}.",
                   (f"{_money(new_rent)} is above that limit, so this is a likely violation unless the landlord can "
                    "show added repair costs or the tenant agreed to it before the emergency."
                    if over else f"{_money(new_rent)} is at or under the limit.")]
        return _result("likely_violation" if over else "within_limit", county, reasons, limit=limit, pct=pct,
                       basis="pre_emergency_plus_10", em=em, unverified=unv)

    if beds is None or beds < 0:
        return _result("unclear", county, [
            inside, "This unit wasn't rented or offered before the emergency, so the limit is 160% of HUD's Fair "
                    "Market Rent. Tell us the number of bedrooms."], basis="fmr_160", em=em, unverified=unv)
    fmr_data = load_fmr()
    entry = src = None
    safmr = (fmr_data.get("safmr") or {}).get(z)
    cfmr = fmr_data["county_fmr"].get(county)
    if safmr and beds in safmr["rents"]:
        entry, src = safmr, f"{safmr['source']}, ZIP {z}, {beds} bedroom"
    elif cfmr and beds in cfmr["rents"]:
        entry, src = cfmr, f"{cfmr['source']}, {beds} bedroom"
    if entry is None:
        return _result("unclear", county, [
            inside, "We don't have a HUD Fair Market Rent for this place and bedroom count, so we can't compute "
                    "the 160% limit."], basis="fmr_160", em=em, unverified=unv)
    fmr = entry["rents"][beds]
    limit = _down(fmr * Decimal("1.60"))
    reasons = [inside, f"This unit wasn't rented or offered before the emergency, so the limit is 160% of HUD's "
                       f"Fair Market Rent: 160% of {_money(fmr)} is {_money(limit)}."]
    over = new_rent > limit
    if not entry.get("verified", False):
        unv = unv + ["the HUD Fair Market Rent figure"]
        reasons.append("That Fair Market Rent figure has not been checked against HUD's own file, so we can't give "
                       f"a firm answer. {_money(new_rent)} is {'above' if over else 'at or under'} the estimated limit.")
        return _result("unclear", county, reasons, limit=limit, basis="fmr_160", fmr=fmr, fmr_source=src, em=em, unverified=unv)
    reasons.append(f"{_money(new_rent)} is {'above that, so this is a likely violation' if over else 'at or under the limit'}.")
    return _result("likely_violation" if over else "within_limit", county, reasons, limit=limit, basis="fmr_160",
                   fmr=fmr, fmr_source=src, em=em, unverified=unv)
