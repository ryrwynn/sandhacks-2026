"""The only module that talks to Gemini. Owner: lane B.

Every caller (api/routers/, worker/llm_extract.py) uses these functions; nothing else imports
google.genai. Gemini only parses and writes words: it never produces a verdict, forecast or score.
Every function returns None when no usable answer is available (quota used up, timeout, failed
figures_ok), so callers show the numbers alone and never retry.

Quota rules (free tier) are in .claude/agents/lane-rules.md: answers that pass validation are cached
in the llm_cache table (key = sha256 of job + prompt + schema), per-day 429s mark a model used up
until midnight Pacific, and every call is logged without the key.
Models come from PARSE_MODEL, LETTER_MODEL and GEMINI_FALLBACK_MODEL.
"""
import re

from pydantic import BaseModel


class ListingFields(BaseModel):
    beds: int | None = None
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    unit_label: str | None = None
    property_type: str | None = None   # 'apartment' | 'condo' | 'single_family'
    pets_allowed: bool | None = None
    parking: bool | None = None
    in_unit_laundry: bool | None = None
    price_usd: int | None = None       # for social posts; listing sites map price directly
    zip: str | None = None
    neighborhood: str | None = None
    is_rental_offer: bool | None = None


NUMBER = re.compile(r"\$[\d,]+(?:\.\d{2})?|\d+(?:\.\d+)?%")


def figures_ok(text: str, allowed: set[str]) -> bool:
    """Reject text that mentions a dollar amount or percentage the engine didn't produce."""
    return set(NUMBER.findall(text)) <= allowed


# ---- parsing (PARSE_MODEL) ----
def parse_listing(text: str) -> ListingFields | None:
    """Extract listing facts from free text. None when Gemini gives nothing usable."""
    return None  # stub until lane B lands


# ---- writing (LETTER_MODEL); each returns text that passed figures_ok, or None ----
def generate_text(job: str, prompt: str, allowed_figures: set[str],
                  model_env: str = "LETTER_MODEL") -> str | None:
    """Shared path for every text job: cache lookup, call, figures_ok, cache store."""
    return None  # stub until lane B lands


def explain_verdict(check: dict, lang: str) -> str | None:
    """check: the CheckResponse as a dict (verdict, cap_pct, max_legal_rent, overage_*, reasons,
    figures). lang: 'en' | 'es' | 'vi' | 'tl'. Returns 3 to 5 sentences."""
    return None


def draft_letter(check: dict, address: str) -> str | None:
    """Formal English letter citing Civil Code 1947.12, with [Tenant name] and [Landlord name]
    placeholders (names are never sent to Gemini)."""
    return None


def zip_summary(zip_name: str, persona: str, contributions: list[dict]) -> str | None:
    """'Why this ZIP': two plain sentences from the top 3 contributions."""
    return None


def explain_gaps(listing_text: str, gaps: list[dict]) -> str | None:
    """2 to 4 sentences on what's missing and why it matters; never a rewritten listing."""
    return None
