"""The only module that talks to Gemini. Owner: lane B.

Every caller (API routers, worker/llm_extract.py) uses these functions; nothing else imports
google.genai. Gemini only parses and writes words: it never produces a verdict, forecast or score.
Every function returns None when no usable answer is available (quota used up, timeout, failed
figures_ok), so callers show the numbers alone and never retry.

Quota rules (free tier) are in .claude/agents/lane-rules.md: answers that pass validation are cached
in the llm_cache table (key = sha256 of job + prompt + schema), per-day 429s mark a model used up
until midnight Pacific, and every call is logged without the key.
Models come from PARSE_MODEL, LETTER_MODEL and GEMINI_FALLBACK_MODEL.
"""
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
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


log = logging.getLogger("rentorknot.gemini")

TIMEOUT_MS = 20_000
BACKOFF = (1, 2, 4)
PACIFIC = ZoneInfo("America/Los_Angeles")
LANGS = {"en": "English", "es": "Spanish", "vi": "Vietnamese", "tl": "Tagalog"}

_sleep = time.sleep                       # tests replace this so backoff is instant
_client_obj = None
_used_up: dict[str, datetime] = {}        # model -> when its daily quota resets (midnight Pacific)
_no_thinking: set[str] = set()            # models that rejected a thinking level
_db_down_until = 0.0


def _reset_state() -> None:
    """For tests."""
    global _client_obj, _db_down_until
    _client_obj = None
    _db_down_until = 0.0
    _used_up.clear()
    _no_thinking.clear()


# ---- client (lazy: importing this module needs no key) ----
def _get_client():
    global _client_obj
    if _client_obj is None:
        from google import genai
        from google.genai import types
        _client_obj = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=TIMEOUT_MS),
        )
    return _client_obj


# ---- cache (llm_cache table); any database trouble just skips the cache ----
def cache_key(job: str, prompt: str, schema: str) -> str:
    return hashlib.sha256(json.dumps([job, prompt, schema]).encode()).hexdigest()


def _connect():
    global _db_down_until
    url = os.environ.get("DATABASE_URL")
    if not url or time.monotonic() < _db_down_until:
        return None
    try:
        import psycopg
        return psycopg.connect(url, connect_timeout=2, autocommit=True)
    except Exception:
        _db_down_until = time.monotonic() + 60
        return None


def _cache_get(key: str):
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT response FROM llm_cache WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _cache_put(key: str, job: str, model: str, response) -> None:
    conn = _connect()
    if conn is None:
        return
    try:
        from psycopg.types.json import Jsonb
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO llm_cache (key, job, model, response) VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (key) DO NOTHING", (key, job, model, Jsonb(response)))
    except Exception:
        pass


# ---- error classification ----
def _quota_ids(obj) -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "quotaId" and isinstance(v, str):
                found.append(v)
            else:
                found += _quota_ids(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _quota_ids(v)
    return found


def _classify(exc: Exception) -> str:
    """'daily' | 'retry' | 'thinking' | 'fail'"""
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, TimeoutError)):
        return "retry"
    code = getattr(exc, "code", None)
    if code == 429:
        if any("PerDay" in q for q in _quota_ids(getattr(exc, "details", None))):
            return "daily"
        return "retry"
    if code in (500, 502, 503, 504):
        return "retry"
    if code == 400 and "thinking" in str(exc).lower():
        return "thinking"
    return "fail"


def _next_midnight_pacific() -> datetime:
    now = datetime.now(PACIFIC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _is_used_up(model: str) -> bool:
    until = _used_up.get(model)
    if until and datetime.now(PACIFIC) < until:
        return True
    _used_up.pop(model, None)
    return False


def _thinking_level(model: str) -> str | None:
    if "gemini-3" not in model or model in _no_thinking:
        return None
    return "minimal" if "flash" in model else "low"


def _request(model: str, prompt: str, schema_cls, job: str):
    """One real request. Returns the response; raises on failure."""
    from google.genai import types
    kw = {"temperature": 0}
    if schema_cls is not None:
        kw.update(response_mime_type="application/json", response_schema=schema_cls)
    level = _thinking_level(model)
    if level:
        kw["thinking_config"] = types.ThinkingConfig(thinking_level=level)
    started = time.monotonic()
    status = "ok"
    try:
        return _get_client().models.generate_content(
            model=model, contents=prompt, config=types.GenerateContentConfig(**kw))
    except Exception as e:
        status = str(getattr(e, "code", None) or type(e).__name__)
        raise
    finally:
        log.info("gemini call job=%s model=%s status=%s duration_ms=%d cache_hit=False",
                 job, model, status, (time.monotonic() - started) * 1000)


def _run(job: str, prompt: str, schema_cls, model_env: str):
    """Primary model (first try + 3 retries), then the fallback once. (model, response) or None."""
    primary = os.environ.get(model_env)
    fallback = os.environ.get("GEMINI_FALLBACK_MODEL")
    models = [m for m in (primary,) if m]
    if fallback and fallback != primary:
        models.append(fallback)
    for i, model in enumerate(models):
        if _is_used_up(model):
            log.info("gemini skip job=%s model=%s status=used_up duration_ms=0 cache_hit=False", job, model)
            continue
        waits = list(BACKOFF) if i == 0 else []
        while True:
            try:
                return model, _request(model, prompt, schema_cls, job)
            except Exception as e:
                kind = _classify(e)
                if kind == "thinking" and _thinking_level(model):
                    _no_thinking.add(model)
                    continue
                if kind == "daily":
                    _used_up[model] = _next_midnight_pacific()
                    break
                if kind == "retry" and waits:
                    _sleep(waits.pop(0))
                    continue
                break
    return None


def _cached_call(job: str, prompt: str, allowed: set[str] | None, model_env: str, schema_cls=None):
    """Cache lookup, call, validation, cache store. Returns text (str) or a parsed dict, or None."""
    schema = json.dumps(schema_cls.model_json_schema(), sort_keys=True) if schema_cls else "text"
    key = cache_key(job, prompt, schema)
    hit = _cache_get(key)
    if hit is not None:
        log.info("gemini cache job=%s model=- status=hit duration_ms=0 cache_hit=True", job)
        if schema_cls:
            return hit
        text = hit.get("text") if isinstance(hit, dict) else None
        return text if text and figures_ok(text, allowed or set()) else None
    got = _run(job, prompt, schema_cls, model_env)
    if got is None:
        return None
    model, resp = got
    try:
        if schema_cls:
            value = schema_cls.model_validate_json(resp.text).model_dump()
        else:
            value = (resp.text or "").strip()
            if not value or not figures_ok(value, allowed or set()):
                return None
    except Exception:
        return None
    _cache_put(key, job, model, value if schema_cls else {"text": value})
    return value


# ---- parsing (PARSE_MODEL) ----
def parse_listing(text: str) -> ListingFields | None:
    """Extract listing facts from free text. None when Gemini gives nothing usable."""
    try:
        prompt = ("Extract these fields from the rental listing. Use null when a field isn't stated. "
                  "Do not guess.\n\n" + text)
        out = _cached_call("parse_listing", prompt, None, "PARSE_MODEL", ListingFields)
        return ListingFields(**out) if out else None
    except Exception:
        return None


# ---- writing (LETTER_MODEL); each returns text that passed figures_ok, or None ----
def generate_text(job: str, prompt: str, allowed_figures: set[str],
                  model_env: str = "LETTER_MODEL") -> str | None:
    """Shared path for every text job: cache lookup, call, figures_ok, cache store."""
    try:
        return _cached_call(job, prompt, set(allowed_figures), model_env)
    except Exception:
        return None


def _numbers(*things) -> set[str]:
    return set(NUMBER.findall(json.dumps(things, default=str)))


def _check_figures(check: dict) -> set[str]:
    return set(check.get("figures") or []) | _numbers(check.get("reasons") or [])


def _check_facts(check: dict) -> str:
    keys = ("verdict", "cap_pct", "max_legal_rent", "increase_pct", "overage_monthly",
            "overage_yearly", "third_increase")
    facts = {k: check.get(k) for k in keys}
    facts["reasons"] = check.get("reasons") or []
    facts["figures_you_may_cite"] = sorted(_check_figures(check))
    return json.dumps(facts, indent=1, default=str)


RULES = ("Use only the dollar amounts and percentages listed in figures_you_may_cite, written exactly as "
         "shown. Do not compute or invent any other number. Do not give legal advice or promise outcomes.")


def explain_verdict(check: dict, lang: str) -> str | None:
    """check: the CheckResponse as a dict (verdict, cap_pct, max_legal_rent, overage_*, reasons,
    figures). lang: 'en' | 'es' | 'vi' | 'tl'. Returns 3 to 5 sentences."""
    try:
        language = LANGS.get(lang, "English")
        prompt = (f"Explain this California rent-increase check to a renter in {language}, in 3 to 5 plain "
                  "sentences. The verdict was already decided by software; restate it, do not change it. "
                  f"{RULES}\n\n{_check_facts(check)}")
        return generate_text(f"explain_verdict:{lang}", prompt, _check_figures(check))
    except Exception:
        return None


def draft_letter(check: dict, address: str) -> str | None:
    """Formal English letter citing Civil Code 1947.12, with [Tenant name] and [Landlord name]
    placeholders (names are never sent to Gemini)."""
    try:
        prompt = ("Write a short, formal, polite English letter from a tenant to a landlord disputing a rent "
                  "increase under California Civil Code section 1947.12 (AB 1482). Use the placeholders "
                  "[Tenant name] and [Landlord name] exactly; do not invent names. Refer to the rental at: "
                  f"{address}. Ask the landlord to withdraw or correct the increase. {RULES}\n\n"
                  f"{_check_facts(check)}")
        return generate_text("draft_letter", prompt, _check_figures(check))
    except Exception:
        return None


def zip_summary(zip_name: str, persona: str, contributions: list[dict]) -> str | None:
    """'Why this ZIP': two plain sentences from the top 3 contributions."""
    try:
        prompt = (f"In exactly two plain sentences, say why {zip_name} scores well for the '{persona}' "
                  "profile, using only the contributions below. Do not mention who lives there. "
                  "Use only dollar amounts and percentages that appear below.\n\n"
                  + json.dumps(contributions, indent=1, default=str))
        return generate_text("zip_summary", prompt, _numbers(contributions))
    except Exception:
        return None


def explain_gaps(listing_text: str, gaps: list[dict]) -> str | None:
    """2 to 4 sentences on what's missing and why it matters; never a rewritten listing."""
    try:
        prompt = ("In 2 to 4 plain sentences, explain what is missing from this rental listing and why it "
                  "matters to renters. Do not rewrite the listing. Use only dollar amounts and percentages "
                  f"that appear below.\n\nGaps found:\n{json.dumps(gaps, indent=1, default=str)}\n\n"
                  f"Listing:\n{listing_text}")
        return generate_text("listing_gaps", prompt, _numbers(gaps, listing_text))
    except Exception:
        return None


# ---- needs parsing (PARSE_MODEL): plain language to constraints (night-match) ----
class NeedsFields(BaseModel):
    budget_min_usd: float | None = None
    budget_max_usd: float | None = None
    beds_min: int | None = None
    beds_max: int | None = None
    zips: list[str] = []
    areas: list[str] = []
    property_types: list[str] = []      # 'apartment' | 'condo' | 'single_family' | 'townhouse'
    must_haves: list[str] = []          # lowercase single words: pets, parking, laundry, ...
    nice_to_haves: list[str] = []
    commute_anchors: list[str] = []


def parse_needs(text: str) -> dict | None:
    """Constraints from a renter's description, cached by text. None when Gemini gives nothing usable."""
    try:
        prompt = ("Turn this renter's description into search constraints. Use null or an empty list when "
                  "something isn't stated; do not guess. Studio means beds 0. Must-haves are things the "
                  "renter requires (pets, parking, laundry, ...); nice-to-haves are preferences. Commute "
                  "anchors are places they want to be near. Describe only the home; ignore anything about "
                  "the renter as a person.\n\n" + text)
        return _cached_call("parse_needs", prompt, None, "PARSE_MODEL", NeedsFields)
    except Exception:
        return None


# ---- Facebook group posts, about 10 per request (PARSE_MODEL, a Flash Lite model on the free tier) ----
class PostFields(BaseModel):
    i: int                                   # the post's number in the prompt
    is_rental_offer: bool | None = None
    price_usd: int | None = None
    beds: int | None = None
    baths: float | None = None
    unit_type: str | None = None             # 'entire_unit' | 'room' | 'sublet'
    neighborhood: str | None = None
    zip: str | None = None
    available_date: str | None = None        # YYYY-MM-DD
    pets_allowed: bool | None = None
    parking: bool | None = None
    laundry: bool | None = None
    utilities_included: bool | None = None


class PostBatch(BaseModel):
    posts: list[PostFields] = []


POSTS_PROMPT = (
    "Each numbered item below is a post from a San Diego housing group. For every item return one object "
    "with its number i. is_rental_offer is true only when the post offers a place for rent (not someone "
    "looking for a place or a roommate, not an ad for a service). price_usd is the monthly rent (the lowest "
    "if several). beds: bedrooms offered (studio = 0; a single room for rent = 1). unit_type: 'entire_unit' "
    "for a whole apartment or house, 'room' for a room in a shared home, 'sublet' for a temporary sublease. "
    "neighborhood: the San Diego neighborhood or city named in the post. zip: only a 5-digit ZIP written in "
    "the post. available_date as YYYY-MM-DD (today is {today}). laundry is true for in-unit or on-site "
    "laundry. Use null for anything the post doesn't state; do not guess. Never include names, phone "
    "numbers or emails.\n\n")


def parse_posts(texts: list[str], today: str) -> list[dict] | None:
    """Fields for a batch of (already redacted) posts, cached by the batch. None when Gemini gives nothing.
    Callers validate each returned item on its own: a bad item never sinks the batch."""
    try:
        body = "\n\n".join(f"[{i}] {t.strip()[:1500]}" for i, t in enumerate(texts))
        out = _cached_call("parse_fb_posts", POSTS_PROMPT.format(today=today) + body, None, "PARSE_MODEL",
                           PostBatch)
        return list(out.get("posts") or []) if out else None
    except Exception:
        return None


# ---- embeddings (gemini-embedding-2, 768 dimensions, at most EMBED_REQUEST_BUDGET requests) ----
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIMS = 768
QUERY_PREFIX = "task: search result | query: "
_embed_spent = 0                          # requests this process has sent (the DB row below is the total)
_BUDGET_KEY = "embed_requests_total"


def embed_budget() -> int:
    try:
        return int(os.environ.get("EMBED_REQUEST_BUDGET", "900"))
    except ValueError:
        return 900


def embed_spent() -> int:
    """Total embedding requests sent so far (persisted in llm_cache so it survives restarts)."""
    conn = _connect()
    if conn is not None:
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT response FROM llm_cache WHERE key = %s", (_BUDGET_KEY,))
                row = cur.fetchone()
                return max(int(row[0].get("n", 0)) if row else 0, _embed_spent)
        except Exception:
            pass
    return _embed_spent


def _embed_bump() -> None:
    global _embed_spent
    _embed_spent += 1
    conn = _connect()
    if conn is None:
        return
    try:
        from psycopg.types.json import Jsonb
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO llm_cache (key, job, model, response) VALUES (%s, 'embed_budget', %s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET response = jsonb_set(llm_cache.response, '{n}', "
                        "to_jsonb(COALESCE((llm_cache.response->>'n')::int, 0) + 1))",
                        (_BUDGET_KEY, EMBED_MODEL, Jsonb({"n": 1})))
    except Exception:
        pass


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """One request, one 768-number vector per text (texts already carry their prefix). None when the
    budget or the daily quota is used up, or on any failure: never retried, so no loop can drain quota."""
    if not texts or _is_used_up(EMBED_MODEL) or embed_spent() >= embed_budget():
        return None
    started = time.monotonic()
    status = "ok"
    try:
        from google.genai import types
        _embed_bump()
        res = _get_client().models.embed_content(
            model=EMBED_MODEL,
            contents=[types.Content(parts=[types.Part.from_text(text=t)]) for t in texts],
            config=types.EmbedContentConfig(output_dimensionality=EMBED_DIMS))
        vecs = [list(e.values) for e in res.embeddings]
        if len(vecs) != len(texts) or any(len(v) != EMBED_DIMS for v in vecs):
            status = "bad_shape"
            return None
        return vecs
    except Exception as e:
        status = str(getattr(e, "code", None) or type(e).__name__)
        if _classify(e) == "daily" or getattr(e, "code", None) == 429:
            _used_up[EMBED_MODEL] = _next_midnight_pacific()
        return None
    finally:
        log.info("gemini call job=embed model=%s status=%s duration_ms=%d cache_hit=False n=%d",
                 EMBED_MODEL, status, (time.monotonic() - started) * 1000, len(texts))


def embed_query(text: str) -> list[float] | None:
    """Vector for a needs description, cached by text (a repeat question spends no request)."""
    try:
        key = cache_key("embed_query", QUERY_PREFIX + text, f"{EMBED_MODEL}:{EMBED_DIMS}")
        hit = _cache_get(key)
        if isinstance(hit, dict) and isinstance(hit.get("v"), list):
            return hit["v"]
        got = embed_texts([QUERY_PREFIX + text])
        if not got:
            return None
        _cache_put(key, "embed_query", EMBED_MODEL, {"v": got[0]})
        return got[0]
    except Exception:
        return None


def document_text(title: str | None, text: str) -> str:
    return f"title: {title or 'none'} | text: {text}"
