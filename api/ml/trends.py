"""ZIP and listing trend metrics (night-forecast). Market signals, never legal findings."""


def zip_trends(zip_: str) -> dict:
    """Return the fields of contracts.api_models.ZipTrendsResponse."""
    raise NotImplementedError


def listing_trends(listing_id: int) -> dict | None:
    """Return the fields of contracts.api_models.ListingTrendsResponse, or None for an unknown listing."""
    raise NotImplementedError
