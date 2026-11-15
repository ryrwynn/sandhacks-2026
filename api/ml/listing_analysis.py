"""Owner-mode listing analysis: completeness, readability, gaps vs. comparables. Owner: lane C.

A prediction from comparable listings, never measured clicks. Never writes a replacement listing.
"""
import re

FACTS = ["price", "beds", "baths", "sqft", "pets", "parking", "laundry", "utilities", "move_in"]
GAP_MIN_SHARE = 0.5

_PATTERNS = {
    "price": r"\$\s?\d|\d\s*(/|per)\s*(mo|month)|\brent\s*(is|:)?\s*\d",
    "beds": r"\b(\d+|one|two|three|four|five)[\s-]*(bed|bd|br|bedroom)s?\b|\bstudio\b",
    "baths": r"\b(\d+(\.\d)?|one|two|three)[\s-]*(bath|ba)s?\b|\bbathrooms?\b",
    "sqft": r"\b\d[\d,]*\s*(sq\.?\s*ft\.?|sqft|square\s*(feet|foot|ft))|\bsf\b",
    "pets": r"\bpets?\b|\bdogs?\b|\bcats?\b",
    "parking": r"\bparking\b|\bgarage\b|\bcarport\b|\bdriveway\b",
    "laundry": r"\blaundry\b|\bwasher\b|\bdryer\b|\bw/d\b",
    "utilities": r"\butilit(y|ies)\b|\bwater\b.{0,20}\bincluded\b|\bincluded\b.{0,20}\b(water|trash|gas|electric)|\btrash\b",
    "move_in": r"move[- ]?in|\bavailable\b|\bavail\b|\bready (now|to move)",
}
_RX = {k: re.compile(v, re.I) for k, v in _PATTERNS.items()}


def percentile_of(value: float, comparables: list[float]) -> float | None:
    """Share of comparables priced below value, 0 to 100. None if there are none."""
    if not comparables:
        return None
    return 100.0 * sum(1 for c in comparables if c < value) / len(comparables)


def detect_facts(text: str) -> dict[str, bool]:
    return {f: bool(_RX[f].search(text or "")) for f in FACTS}


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith("le") and n > 1:
        n -= 1
    return max(n, 1)


def readability(text: str) -> float:
    """Flesch reading ease clipped to 0-100 (0 for empty text)."""
    words = re.findall(r"[A-Za-z']+", text or "")
    if not words:
        return 0.0
    sentences = max(len([s for s in re.split(r"[.!?\n]+", text) if s.strip()]), 1)
    syll = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syll / len(words))
    return round(min(max(score, 0.0), 100.0), 1)


def analyze_listing(text: str, comparable_texts: list[str],
                    price_percentile: float | None = None) -> dict:
    """Returns {"completeness": 0-100, "readability": 0-100, "reach_score": 0-100,
    "stated": {fact: bool}, "gaps": [{"fact", "share_of_comparables"}]} where gaps are facts most
    comparables state that this listing doesn't. reach_score = completeness x a price-position factor
    (cheaper relative to comparables = higher factor)."""
    stated = detect_facts(text)
    completeness = 100.0 * sum(stated.values()) / len(FACTS)
    n = len(comparable_texts)
    gaps = []
    if n:
        comp = [detect_facts(t) for t in comparable_texts]
        for f in FACTS:
            share = sum(c[f] for c in comp) / n
            if not stated[f] and share >= GAP_MIN_SHARE:
                gaps.append({"fact": f, "share_of_comparables": round(share, 2)})
        gaps.sort(key=lambda g: -g["share_of_comparables"])
    # price factor: 1.0 for the cheapest, 0.5 for the priciest, 0.75 when position is unknown
    pct = 50.0 if price_percentile is None else min(max(price_percentile, 0.0), 100.0)
    factor = 1.0 - 0.5 * pct / 100
    return {"completeness": round(completeness, 1), "readability": readability(text),
            "reach_score": round(completeness * factor, 1), "stated": stated, "gaps": gaps}
