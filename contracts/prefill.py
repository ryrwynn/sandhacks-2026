"""Sprint step 0: prefill query parameters for every form (docs/SPRINT.md, "Prefill parameters").

The single source of truth for both the web forms (frontend/src/lib/prefill.ts is generated from this file by
scripts/gen-prefill.py) and the MCP server's form links. A page only fills its fields from these parameters;
it never submits on its own. Values are plain strings: dates YYYY-MM-DD; yes/no/unsure answers `yes`, `no`,
`unsure`; home type one of HOME_TYPES.
"""
from urllib.parse import urlencode

YES_NO = ("yes", "no", "unsure")
HOME_TYPES = ("apartment", "condo", "townhouse", "single_family", "unknown")

# form id -> {"path": page path, "params": {name: meaning}}. Parameter names are exactly these, nothing else.
PREFILL: dict[str, dict] = {
    "renter": {
        "path": "/renter",
        "label": "Rent Cap (AB 1482 increase check)",
        "params": {
            "address": "street address",
            "zip": "5-digit ZIP",
            "year_built": "year built (existing name used by the apartment page link; same as year)",
            "lowest": "lowest rent in the last 12 months, USD",
            "new": "new rent, USD",
            "effective": "date the new rent starts, YYYY-MM-DD",
            "year": "year built",
            "type": "home type (apartment|condo|townhouse|single_family|unknown)",
            "increases": "number of increases in the last 12 months",
            "notice": "got an AB 1482 exemption notice (yes|no|unsure)",
            "corp": "owner is a corporation or REIT (yes|no|unsure)",
        },
    },
    "listing": {
        "path": "/renter",
        "fixed": {"tab": "listing"},
        "label": "Check this price (fair rent for a listing)",
        "params": {
            "zip": "5-digit ZIP",
            "beds": "bedrooms (0 = studio)",
            "asking": "asking rent, USD",
            "baths": "bathrooms",
            "sqft": "square feet",
            "type": "home type",
            "text": "listing text",
        },
    },
    "gouging": {
        "path": "/gouging",
        "label": "Emergency Rent Limits (Penal Code 396)",
        "params": {
            "zip": "5-digit ZIP",
            "beds": "bedrooms",
            "new": "new or offered rent, USD",
            "date": "date the price was charged or offered, YYYY-MM-DD",
            "before": "rent before the emergency, USD",
        },
    },
    "owner": {
        "path": "/owner",
        "label": "Owner price position",
        "params": {
            "zip": "5-digit ZIP",
            "beds": "bedrooms",
            "target": "target rent, USD",
            "sqft": "square feet",
            "year": "year built",
            "type": "home type",
            "lowest": "current tenant's lowest rent in the last 12 months, USD",
            "effective": "date the new rent starts, YYYY-MM-DD",
            "notice": "gave an AB 1482 exemption notice (yes|no|unsure)",
            "corp": "owner is a corporation or REIT (yes|no|unsure)",
        },
    },
    "owner_reach": {
        "path": "/owner/reach",
        "label": "Owner reach",
        "params": {"zip": "5-digit ZIP", "beds": "bedrooms", "ask": "asking rent, USD", "text": "listing text"},
    },
    "buyer": {
        "path": "/buyer",
        "label": "Buyer (Wealth builder)",
        "params": {"budget": "home price budget, USD", "beds": "bedrooms"},
    },
    "find": {
        "path": "/find",
        "label": "Find apartments",
        "params": {
            "zip": "5-digit ZIP",
            "beds": "bedrooms",
            "type": "home type",
            "max": "max rent, USD",
            "source": "listing source",
            "unit": "unit type",
            "sort": "sort order",
            "page": "page number, from 1",
            "per": "results per page (15|30|60)",
            "starter_budget": "opens the Starter finder panel with this monthly budget, USD",
            "starter_beds": "Starter finder bedrooms",
        },
    },
    "advisor": {
        "path": "/advisor",
        "label": "Advisor",
        "params": {"needs": "plain-language needs for Find by needs", "ask": "advisor question (typed in, not sent)"},
    },
}


def form_url(form: str, base: str = "", **values) -> str:
    """Link to a form filled with `values`. Unknown names raise; None and '' are left out."""
    spec = PREFILL[form]
    bad = set(values) - set(spec["params"])
    if bad:
        raise ValueError(f"{form} has no prefill parameter {sorted(bad)}")
    q = dict(spec.get("fixed", {}))
    q.update({k: _s(v) for k, v in values.items() if v is not None and v != ""})
    return base + spec["path"] + ("?" + urlencode(q) if q else "")


def _s(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
