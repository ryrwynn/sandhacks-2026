"""CanonicalListing: what every source adapter must produce (docs/PLAN.md "Source adapters")."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Precision = Literal["address", "street", "zip", "neighborhood", "city"]


class CanonicalListing(BaseModel):
    source_key: str                        # 'zillow_rent', 'apartments_com', 'facebook_groups', ...
    external_id_hash: str                  # sha256 of the source's id; raw ids stay in raw_records
    listing_type: Literal["rent", "sale"]
    observed_at: datetime
    price_usd: int                         # monthly rent or sale price; the low end of a range
    price_max_usd: int | None = None       # the high end, when the source gives a range
    beds: int | None = None                # 0 = studio
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    property_type: str | None = None       # 'apartment' | 'condo' | 'single_family' | 'townhouse' | ...
    address_norm: str | None = None
    unit_label: str | None = None
    zip: str | None = None
    neighborhood: str | None = None
    lat: float | None = None
    lng: float | None = None
    location_precision: Precision
    text_redacted: str | None = None       # description with names, phones and emails removed
    extras: dict = Field(default_factory=dict)            # source-only fields: amenities, pet policy, floor plan
    field_confidence: dict[str, float] = Field(default_factory=dict)  # 1.0 = mapped; lower = extracted
    extraction: Literal["mapped", "llm", "mixed"] = "mapped"
    # Listing price history from the source, oldest first: [{"date": "2026-01-05", "price_usd": 2400,
    # "event": "price_change"}]. Loaded as price_observations with event='history'. Never invented.
    price_history: list[dict] = Field(default_factory=list)
