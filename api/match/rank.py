"""Ranking: hard filters, then price fit, amenity fit, fair-rent position and semantic similarity.

Inputs are prices, listing text, area amenity counts (OSM) and embeddings only. Never who lives in a ZIP.
Points: price_fit 30, amenity_fit 25, fair_rent 20, semantic 25 (total 100). Without embeddings the
semantic 25 points come from keyword overlap and the response says method = "keywords".
"""
import re

from api import db
from api.llm import gemini
from api.match import needs as needs_mod
from api.match import store
from api.ml.listing_analysis import detect_facts
from api.routers._common import safe
from api.routers.tracker import summary
from contracts.api_models import MatchRequest, MatchResponse, MatchResult, ParsedNeeds

W = {"price_fit": 30.0, "amenity_fit": 25.0, "fair_rent": 20.0, "semantic": 25.0}
FAIR = {"below_typical_range": 1.0, "in_range": 0.7, "above_typical_range": 0.2}
AREA_KEYS = ("transit_stops", "groceries", "parks", "food_drink", "gyms")
NICE_AREA = {"transit": "transit_stops", "grocery": "groceries", "parks": "parks", "gym": "gyms",
             "walkable": "food_drink"}
FACT_KEY = {"pets": "pets", "parking": "parking", "laundry": "laundry"}
TYPE_MAP = {"apartment": {"apartment"}, "condo": {"condo"}, "single_family": {"single_family"},
            "townhouse": {"townhouse"}}


def merge_needs(n: ParsedNeeds, req: MatchRequest) -> ParsedNeeds:
    n = n.model_copy()
    if req.budget_max_usd is not None:
        n.budget_max_usd = req.budget_max_usd
    if req.beds_min is not None:
        n.beds_min = req.beds_min
    return n


def hard_filter(rows: list[dict], n: ParsedNeeds) -> list[dict]:
    zips = {z for z in n.zips}
    out = []
    for r in rows:
        if not r.get("active") or r.get("cur") is None:
            continue
        price = float(r["cur"])
        if n.budget_max_usd is not None and price > n.budget_max_usd:
            continue
        if n.budget_min_usd is not None and price < n.budget_min_usd * 0.7:
            continue
        beds = r.get("beds")
        if n.beds_min is not None and (beds is None or beds < n.beds_min):
            continue
        if n.beds_max is not None and (beds is None or beds > n.beds_max):
            continue
        if zips and (r.get("zip") or "").strip() not in zips:
            continue
        if n.property_types and r.get("property_type") not in set().union(*(TYPE_MAP[t] for t in n.property_types)):
            continue
        out.append(r)
    return out


def _percentiles(feats: dict[str, dict], key: str) -> dict[str, float]:
    vals = sorted(float(f[key]) for f in feats.values() if f.get(key) is not None)
    if not vals:
        return {}
    return {z: sum(v <= float(f[key]) for v in vals) / len(vals) for z, f in feats.items() if f.get(key) is not None}


def price_fit(price: float, n: ParsedNeeds) -> float:
    if n.budget_max_usd:
        ratio = price / n.budget_max_usd
        return 1.0 if ratio <= 0.8 else max(0.4, 1.0 - 3.0 * (ratio - 0.8))
    return 0.5


def keyword_score(text: str, n: ParsedNeeds) -> float:
    words = [w.lower() for w in n.nice_to_haves + n.commute_anchors + n.areas]
    if not words:
        return 0.5
    t = text.lower()
    return sum(1 for w in words if w in t) / len(words)


def amenity_fit(facts: dict[str, bool], text: str, zip_: str, n: ParsedNeeds, pct: dict[str, dict[str, float]]):
    """(0..1, stated must-haves, unconfirmed must-haves, nice-to-haves found)"""
    stated, unconfirmed = [], []
    for m in n.must_haves:
        key = FACT_KEY.get(m)
        ok = facts.get(key, False) if key else (m.lower() in text.lower())
        (stated if ok else unconfirmed).append(m)
    must = (len(stated) + 0.3 * len(unconfirmed)) / len(n.must_haves) if n.must_haves else 1.0
    tl = text.lower()
    nice_found = [x for x in n.nice_to_haves if (FACT_KEY.get(x) and facts.get(FACT_KEY[x])) or x.lower() in tl]
    nice = len(nice_found) / len(n.nice_to_haves) if n.nice_to_haves else 0.5
    wanted = [NICE_AREA[x] for x in n.nice_to_haves if x in NICE_AREA]
    keys = wanted or list(AREA_KEYS)
    vals = [pct[k][zip_] for k in keys if zip_ in pct.get(k, {})]
    area = sum(vals) / len(vals) if vals else 0.5
    return 0.6 * must + 0.15 * nice + 0.25 * area, stated, unconfirmed, nice_found, area


def match(req: MatchRequest) -> MatchResponse:
    """Hard filters, then price fit + amenity fit + fair-rent position + semantic similarity. Never demographics."""
    n = merge_needs(needs_mod.parse_needs(req.text), req)
    rows = safe(store.candidates, default=[])
    cands = [r for r in rows if r.get("cur") is not None]
    kept = hard_filter(cands, n)
    ids = [r["listing_id"] for r in kept]
    texts = safe(store.texts, ids, default={})
    feats = safe(db.zip_features, default={})
    pct = {k: _percentiles(feats, k) for k in AREA_KEYS}

    cos: dict[int, float] = {}
    qv = gemini.embed_query(req.text) if kept else None
    if qv:
        cos = safe(store.cosines, qv, ids, gemini.EMBED_MODEL, default={})
    method = "embeddings" if cos else "keywords"
    lo, hi = (min(cos.values()), max(cos.values())) if cos else (0.0, 1.0)

    scored = []
    for r in kept:
        lid, price, zip_ = r["listing_id"], float(r["cur"]), (r["zip"] or "").strip()
        text = texts.get(lid, "")
        facts = detect_facts(text)
        am, stated, unconf, nice_found, area = amenity_fit(facts, text, zip_, n, pct)
        label = None
        try:
            from api.routers.tracker import group_label
            label = group_label(zip_, r["beds"], price) if r["listing_type"] == "rent" else None
        except Exception:
            label = None
        if lid in cos:
            sem = 0.5 if hi - lo < 1e-9 else (cos[lid] - lo) / (hi - lo)
        elif method == "embeddings":
            sem = 0.0                      # no vector for this listing yet
        else:
            sem = keyword_score(text, n)
        comp = {"price_fit": round(W["price_fit"] * price_fit(price, n), 1),
                "amenity_fit": round(W["amenity_fit"] * am, 1),
                "fair_rent": round(W["fair_rent"] * FAIR.get(label, 0.5), 1),
                "semantic": round(W["semantic"] * sem, 1)}
        reasons = []
        if n.budget_max_usd and price <= n.budget_max_usd:
            reasons.append(f"Asking ${price:,.0f}, within your ${n.budget_max_usd:,.0f} budget.")
        if stated:
            reasons.append("States " + ", ".join(stated) + ", which you asked for.")
        if label == "below_typical_range":
            reasons.append("Priced below the typical range for similar listings in its ZIP.")
        elif label == "in_range":
            reasons.append("Priced within the typical range for similar listings in its ZIP.")
        if nice_found:
            reasons.append("Mentions " + ", ".join(nice_found) + ".")
        if area >= 0.66 and not n.nice_to_haves:
            reasons.append("The area has above-typical counts of nearby transit, shops and parks.")
        if comp["semantic"] >= 0.6 * W["semantic"]:
            reasons.append("Its description is close to what you described.")
        scored.append((sum(comp.values()), r, comp, reasons, unconf))
    scored.sort(key=lambda s: (-s[0], float(s[1]["cur"])))
    top = scored[:req.limit]
    obs: dict[int, list] = {}
    if top:
        for o in safe(db.listing_observations, [s[1]["listing_id"] for s in top], default=[]):
            obs.setdefault(o["listing_id"], []).append(o)
    results = [MatchResult(listing=summary(r, obs.get(r["listing_id"], [])), score=round(sc, 1), components=comp,
                           reasons=reasons or ["Passes your filters."], unconfirmed=unconf)
               for sc, r, comp, reasons, unconf in top]
    return MatchResponse(needs=n, results=results, n_candidates=len(cands), n_after_filters=len(kept), method=method)
