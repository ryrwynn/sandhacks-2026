"""Needs parser: plain language to constraints. Gemini first (cached by text), rules when it fails."""
import re

from api import db
from api.llm import gemini
from contracts.api_models import ParsedNeeds

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
# phrase in the text -> normal must-have name
FACTS = {
    "pets": r"\bpets?\b|\bdogs?\b|\bcats?\b|\bpuppy\b|\bkitten\b",
    "parking": r"\bparking\b|\bgarage\b|\bcarport\b",
    "laundry": r"\blaundry\b|\bwasher\b|\bw/d\b",
}
NICE = {"quiet": r"\bquiet\b", "walkable": r"\bwalk(able|ing)\b", "transit": r"\btransit\b|\bbus\b|\btrolley\b",
        "gym": r"\bgym\b", "parks": r"\bparks?\b", "grocery": r"\bgrocer(y|ies)\b", "dishwasher": r"\bdishwasher\b",
        "balcony": r"\bbalcon(y|ies)\b", "ac": r"\bair[- ]?conditioning\b|\ba/c\b"}
TYPES = {"apartment": r"\bapartments?\b", "condo": r"\bcondos?\b", "single_family": r"\bhouse\b|\bsingle[- ]family\b",
         "townhouse": r"\btownhouse\b|\btownhome\b"}
CANON_MUST = {"pet": "pets", "pets": "pets", "dog": "pets", "dogs": "pets", "cat": "pets", "cats": "pets",
              "parking": "parking", "garage": "parking", "laundry": "laundry", "washer": "laundry"}
_money = r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?"


def _amount(m: re.Match) -> float:
    v = float(m.group(1).replace(",", ""))
    return v * 1000 if m.group(2) else v


def _zip_for_area(area: str) -> list[str]:
    a = area.lower().strip()
    return [z for z, n in db.ZIP_NAMES.items() if a and (a in n.lower() or n.lower() in a)]


def rules_parse(text: str) -> ParsedNeeds:
    t = text.lower()
    n = ParsedNeeds(parsed_by="rules")
    mx = re.search(r"(?:under|below|max(?:imum)?|up to|less than|at most|<)\s*" + _money, t)
    mn = re.search(r"(?:over|above|at least|min(?:imum)?|more than)\s*" + _money, t)
    rng = re.search(_money + r"\s*(?:-|to)\s*\$?\s*(\d[\d,]*)", t)
    if rng:
        n.budget_min_usd, n.budget_max_usd = _amount(rng), float(rng.group(3).replace(",", ""))
    else:
        if mx:
            n.budget_max_usd = _amount(mx)
        if mn:
            n.budget_min_usd = _amount(mn)
        if not mx and not mn:
            any_ = re.search(_money, t)
            if any_:
                n.budget_max_usd = _amount(any_)
    if re.search(r"\bstudio\b", t):
        n.beds_min = n.beds_max = 0
    b = re.search(r"\b(\d+|one|two|three|four|five)\s*[- ]?(?:bed(?:room)?s?|br|bd)\b", t)
    if b:
        v = WORDS.get(b.group(1)) if not b.group(1).isdigit() else int(b.group(1))
        if v is not None:
            n.beds_min = v
            n.beds_max = v
            if re.search(rf"{b.group(1)}\s*(?:\+|or more)", t):
                n.beds_max = None
    n.zips = sorted(set(re.findall(r"\b9\d{4}\b", t)))
    for z, name in db.ZIP_NAMES.items():
        if len(name) > 3 and name.lower() in t:
            n.areas.append(name)
            if z not in n.zips:
                n.zips.append(z)
    n.must_haves = [k for k, rx in FACTS.items() if re.search(rx, t)]
    n.nice_to_haves = [k for k, rx in NICE.items() if re.search(rx, t)]
    n.property_types = [k for k, rx in TYPES.items() if re.search(rx, t)]
    n.commute_anchors = [a.strip().title() if a.islower() and len(a) > 4 else a.strip()
                         for a in re.findall(r"(?:near|close to|by)\s+([A-Za-z][A-Za-z .']{1,30}?)(?:[,.;]|\s+(?:with|and|under|for|that)\b|$)",
                                             text)]
    return n


def _clean(f: dict, text: str, fallback: ParsedNeeds) -> ParsedNeeds:
    """Gemini's answer, checked: a budget must appear in the text; ZIPs must be real; names normalised."""
    digits = {re.sub(r"[,$]", "", m) for m in re.findall(r"\$?\d[\d,]*", text)}
    k_amounts = {str(int(float(a) * 1000)) for a in re.findall(r"(\d+(?:\.\d+)?)\s*k\b", text.lower())}
    seen = digits | k_amounts

    def money(v):
        return v if v is not None and v > 0 and str(int(v)) in seen else None

    must = []
    for m in f.get("must_haves") or []:
        c = CANON_MUST.get(str(m).lower().strip(), str(m).lower().strip())
        if c and c not in must:
            must.append(c)
    nice = [str(x).lower().strip() for x in (f.get("nice_to_haves") or []) if str(x).strip()]
    zips = [z for z in (f.get("zips") or []) if re.fullmatch(r"9\d{4}", str(z))]
    areas = [a for a in (f.get("areas") or []) if str(a).strip()]
    for a in areas:
        for z in _zip_for_area(a):
            if z not in zips:
                zips.append(z)
    ptypes = [p for p in (f.get("property_types") or []) if p in ("apartment", "condo", "single_family", "townhouse")]
    mx, mn = money(f.get("budget_max_usd")), money(f.get("budget_min_usd"))
    return ParsedNeeds(
        budget_min_usd=mn, budget_max_usd=mx if mx is not None else fallback.budget_max_usd,
        beds_min=f.get("beds_min") if f.get("beds_min") is not None else fallback.beds_min,
        beds_max=f.get("beds_max") if f.get("beds_max") is not None else fallback.beds_max,
        zips=zips, areas=areas, property_types=ptypes, must_haves=must or fallback.must_haves,
        nice_to_haves=nice, commute_anchors=[str(a) for a in (f.get("commute_anchors") or [])],
        parsed_by="gemini")


def parse_needs(text: str) -> ParsedNeeds:
    """Gemini (cached by text) turns plain language into constraints; a rules fallback when Gemini fails."""
    rules = rules_parse(text)
    try:
        got = gemini.parse_needs(text)
    except Exception:
        got = None
    if not got:
        return rules
    try:
        return _clean(got, text, rules)
    except Exception:
        return rules
