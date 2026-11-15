"""Owner reach: how many fixed renter-need profiles would shortlist a listing. An estimate, never measured demand.

Profiles (documented, fixed rules; the data only sets the budgets and which facts are considered):
- Bedrooms: the listing's own bed count (a studio is never a comparable for a 2-bedroom).
- Budget ceilings: the 10th, 20th ... 90th percentile of comparable rents in the ZIP (rounded to $25),
  each with equal weight, on the assumption that renters' budgets are spread like the prices on offer.
- Must-haves: among pets, parking, laundry, the facts stated by at least 25% of comparable listings
  (all three when there are no comparable texts). Sets: none (40% of demand), each fact alone (40% split
  equally), all together (20%). These shares are assumptions, not measurements.
A profile shortlists the listing when its rent is at or under the ceiling and every must-have is stated.
"""
from api import db
from api.ml.listing_analysis import detect_facts
from api.routers._common import safe
from contracts.api_models import (OwnerReachRequest, OwnerReachResponse, ReachChange, ReachPoint,
                                  ReachProfile)

FACTS = ("pets", "parking", "laundry")
FACT_SHARE = 0.25
SET_WEIGHT = {"none": 0.4, "singles": 0.4, "all": 0.2}
MIN_COMPS = 5
STEPS = (-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15)
PRETTY = {"pets": "pets allowed", "parking": "parking", "laundry": "laundry"}


def _r25(v: float) -> float:
    return round(v / 25) * 25.0


def _pct(sorted_vals: list[float], q: float) -> float:
    i = q * (len(sorted_vals) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def build_profiles(beds: int, rents: list[float], target: float, considered: list[str]) -> list[ReachProfile]:
    if len(rents) >= MIN_COMPS:
        s = sorted(rents)
        ceilings = sorted({_r25(_pct(s, q / 10)) for q in range(1, 10)})
    else:
        ceilings = sorted({_r25(target * f) for f in (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25)})
    sets: list[tuple[list[str], float]] = [([], SET_WEIGHT["none"])]
    for f in considered:
        sets.append(([f], SET_WEIGHT["singles"] / len(considered)))
    if len(considered) > 1:
        sets.append((list(considered), SET_WEIGHT["all"]))
    else:
        sets[0] = ([], SET_WEIGHT["none"] + SET_WEIGHT["all"])
    out = []
    for c in ceilings:
        for must, w in sets:
            label = f"{'studio' if beds == 0 else f'{beds} bedroom'}, up to ${c:,.0f}"
            if must:
                label += ", needs " + " and ".join(PRETTY[m] for m in must)
            out.append(ReachProfile(id=f"p_{beds}br_{int(c)}_{'_'.join(must) or 'none'}", label=label, beds=beds,
                                    max_rent_usd=c, must_haves=must, weight=w / len(ceilings)))
    return out


def reach(profiles: list[ReachProfile], rent: float, stated: dict[str, bool]) -> float:
    total = sum(p.weight for p in profiles) or 1.0
    ok = sum(p.weight for p in profiles if rent <= p.max_rent_usd and all(stated.get(m) for m in p.must_haves))
    return round(100.0 * ok / total, 1)


def owner_reach(req: OwnerReachRequest) -> OwnerReachResponse:
    """Fixed renter-need profiles from comparables; reach at each price and with each missing fact filled."""
    rents = safe(db.comparable_rents, req.zip, req.beds, default=[]) or []
    comp_texts = safe(db.comparable_texts, req.zip, req.beds, default=[]) or []
    considered = list(FACTS)
    if comp_texts:
        shares = {f: sum(detect_facts(t)[f] for t in comp_texts) / len(comp_texts) for f in FACTS}
        considered = [f for f in FACTS if shares[f] >= FACT_SHARE] or list(FACTS)
    stated = dict(req.stated) if req.stated is not None else None
    if stated is None:
        text = req.text
        if not text and req.listing_id is not None:
            text = safe(db.listing_text, req.listing_id, default=None)
        found = detect_facts(text or "")
        stated = {f: found[f] for f in FACTS}
    profiles = build_profiles(req.beds, rents, req.target_rent, considered)
    now = reach(profiles, req.target_rent, stated)
    curve = [ReachPoint(rent_usd=_r25(req.target_rent * (1 + s)) if s else req.target_rent,
                        reach_pct=reach(profiles, _r25(req.target_rent * (1 + s)) if s else req.target_rent, stated))
             for s in STEPS]
    changes = []
    for pt in curve:
        if pt.rent_usd < req.target_rent and pt.reach_pct > now:
            changes.append(ReachChange(kind="price", label=f"Lower the rent to ${pt.rent_usd:,.0f}",
                                       new_rent_usd=pt.rent_usd, reach_before_pct=now, reach_after_pct=pt.reach_pct,
                                       gain_pts=round(pt.reach_pct - now, 1)))
    for f in considered:
        if not stated.get(f):
            after = reach(profiles, req.target_rent, {**stated, f: True})
            if after > now:
                changes.append(ReachChange(kind="fact", label=f"State whether {PRETTY[f]}" if f != "pets"
                                           else "State whether pets are allowed", fact=f, reach_before_pct=now,
                                           reach_after_pct=after, gain_pts=round(after - now, 1)))
    changes.sort(key=lambda c: -c.gain_pts)
    note = (f"Built from {len(rents)} comparable {'studio' if req.beds == 0 else f'{req.beds}-bedroom'} rents in "
            f"{req.zip}: budget ceilings at the 10th to 90th percentile, must-have sets of {', '.join(considered)}. "
            "Profile weights are fixed assumptions. A profile shortlists a listing only if the rent fits and every "
            "must-have is stated.")
    if len(rents) < MIN_COMPS:
        note += " Too few comparables here, so budgets are spread around your target rent instead."
    return OwnerReachResponse(current_reach_pct=now, curve=curve, best_changes=changes[:5], profiles=profiles,
                              n_comparables=len(rents), method_note=note)
