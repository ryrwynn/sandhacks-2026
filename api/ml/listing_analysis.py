"""Owner-mode listing analysis: completeness, readability, gaps vs. comparables. Owner: lane C.

A prediction from comparable listings, never measured clicks. Never writes a replacement listing.
"""

FACTS = ["price", "beds", "baths", "sqft", "pets", "parking", "laundry", "utilities", "move_in"]


def percentile_of(value: float, comparables: list[float]) -> float | None:
    """Share of comparables priced below value, 0 to 100. None if there are none."""
    raise NotImplementedError("lane C: percentile_of")


def analyze_listing(text: str, comparable_texts: list[str],
                    price_percentile: float | None = None) -> dict:
    """Returns {"completeness": 0-100, "readability": 0-100, "reach_score": 0-100,
    "stated": {fact: bool}, "gaps": [{"fact", "share_of_comparables"}]} where gaps are facts most
    comparables state that this listing doesn't. reach_score = completeness x a price-position factor
    (cheaper relative to comparables = higher factor)."""
    raise NotImplementedError("lane C: analyze_listing")
