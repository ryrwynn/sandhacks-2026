"""Gemini layer tests. The network is mocked: no test sends a real request."""
import httpx
import pytest
from google.genai import errors

from api.llm import gemini as g

CHECK = {
    "verdict": "over_cap", "cap_pct": 8.2, "max_legal_rent": 2272.2, "overage_monthly": 77.8,
    "reasons": ["The most your landlord can charge is $2,272.20."],
    "figures": ["$2,272.20", "8.2%", "$77.80"],
}


class Resp:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, script):
        self.script = script          # {model: [outcome, ...]}; Exception raises, str returns text
        self.calls = []
        self.configs = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        self.configs.append(config)
        outcomes = self.script.get(model, [])
        out = outcomes.pop(0) if len(outcomes) > 1 else (outcomes[0] if outcomes else RuntimeError("none"))
        if isinstance(out, Exception):
            raise out
        return Resp(out)


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


def api_error(code, details=None):
    body = {"error": {"code": code, "message": "x", "status": "X", "details": details or []}}
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, body)


def per_minute():
    return api_error(429, [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel"}]}])


def per_day():
    return api_error(429, [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}])


@pytest.fixture
def env(monkeypatch):
    g._reset_state()
    monkeypatch.setenv("PARSE_MODEL", "gemini-3-flash")
    monkeypatch.setenv("LETTER_MODEL", "gemini-3-flash")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sleeps = []
    monkeypatch.setattr(g, "_sleep", sleeps.append)
    store = {}
    monkeypatch.setattr(g, "_cache_get", lambda k: store.get(k))
    monkeypatch.setattr(g, "_cache_put", lambda k, job, model, resp: store.setdefault(k, resp))

    def install(script):
        client = FakeClient(script)
        monkeypatch.setattr(g, "_get_client", lambda: client)
        return client

    yield type("E", (), {"install": staticmethod(install), "sleeps": sleeps, "store": store})
    g._reset_state()


def test_import_needs_no_key():
    assert g._client_obj is None


def test_figures_ok():
    assert g.figures_ok("Pay $2,272.20 at 8.2%.", {"$2,272.20", "8.2%"})
    assert not g.figures_ok("Pay $2,300.", {"$2,272.20"})


def test_success_and_cache_hit_sends_no_request(env):
    c = env.install({"gemini-3-flash": ["Your cap is 8.2%."]})
    assert g.explain_verdict(CHECK, "en") == "Your cap is 8.2%."
    assert len(c.models.calls) == 1
    assert g.explain_verdict(CHECK, "en") == "Your cap is 8.2%."
    assert len(c.models.calls) == 1                      # second call served from cache
    assert g.explain_verdict(CHECK, "es")                # another language is another key
    assert len(c.models.calls) == 2


def test_figures_ok_applied_and_bad_text_not_cached(env):
    env.install({"gemini-3-flash": ["Pay $9,999 now."]})
    assert g.explain_verdict(CHECK, "en") is None
    assert env.store == {}


def test_per_minute_429_retries_with_backoff_then_fallback(env):
    c = env.install({"gemini-3-flash": [per_minute()], "gemini-3.1-flash-lite": ["ok 8.2%"]})
    assert g.explain_verdict(CHECK, "en") == "ok 8.2%"
    assert c.models.calls == ["gemini-3-flash"] * 4 + ["gemini-3.1-flash-lite"]
    assert env.sleeps == [1, 2, 4]


def test_503_retry_then_success(env):
    c = env.install({"gemini-3-flash": [api_error(503), api_error(503), "fine"]})
    assert g.explain_verdict(CHECK, "en") == "fine"
    assert len(c.models.calls) == 3 and env.sleeps == [1, 2]


def test_timeout_treated_like_503(env):
    c = env.install({"gemini-3-flash": [httpx.ReadTimeout("t"), "fine"]})
    assert g.explain_verdict(CHECK, "en") == "fine"
    assert len(c.models.calls) == 2 and env.sleeps == [1]


def test_everything_fails_returns_none(env):
    c = env.install({"gemini-3-flash": [api_error(503)], "gemini-3.1-flash-lite": [api_error(503)]})
    assert g.explain_verdict(CHECK, "en") is None
    assert c.models.calls.count("gemini-3.1-flash-lite") == 1   # fallback tried once, no retries


def test_per_day_429_goes_straight_to_fallback_no_retries(env):
    c = env.install({"gemini-3-flash": [per_day()], "gemini-3.1-flash-lite": ["ok"]})
    assert g.explain_verdict(CHECK, "en") == "ok"
    assert c.models.calls == ["gemini-3-flash", "gemini-3.1-flash-lite"]
    assert env.sleeps == []


def test_used_up_model_is_skipped_on_later_calls(env):
    c = env.install({"gemini-3-flash": [per_day()], "gemini-3.1-flash-lite": ["ok"]})
    g.explain_verdict(CHECK, "en")
    c.models.calls.clear()
    assert g.draft_letter(CHECK, "1 Main St")
    assert c.models.calls == ["gemini-3.1-flash-lite"]          # no request to the used-up model


def test_used_up_resets_after_midnight(env):
    from datetime import datetime, timedelta
    g._used_up["gemini-3-flash"] = datetime.now(g.PACIFIC) - timedelta(seconds=1)
    c = env.install({"gemini-3-flash": ["back"]})
    assert g.explain_verdict(CHECK, "en") == "back"
    assert c.models.calls == ["gemini-3-flash"]


def test_thinking_level_and_timeout_sent(env):
    c = env.install({"gemini-3-flash": ["x"]})
    g.explain_verdict(CHECK, "en")
    assert c.models.configs[0].thinking_config.thinking_level.value.lower() == "minimal"
    assert g.TIMEOUT_MS == 20_000


def test_thinking_rejected_is_dropped(env):
    c = env.install({"gemini-3-flash": [api_error(400, [{"m": "thinking level not supported"}]), "x"]})
    # message must mention thinking for classification
    c.models.script["gemini-3-flash"][0] = errors.ClientError(
        400, {"error": {"code": 400, "message": "Thinking level is not supported", "status": "INVALID_ARGUMENT"}})
    assert g.explain_verdict(CHECK, "en") == "x"
    assert c.models.configs[1].thinking_config is None


def test_parse_listing_validates_and_caches(env):
    c = env.install({"gemini-3-flash": ['{"beds": 2, "baths": 1.5, "pets_allowed": true}']})
    out = g.parse_listing("2br 1.5ba, pets ok")
    assert out.beds == 2 and out.baths == 1.5 and out.pets_allowed is True
    assert g.parse_listing("2br 1.5ba, pets ok").beds == 2
    assert len(c.models.calls) == 1


def test_parse_listing_garbage_is_none(env):
    env.install({"gemini-3-flash": ["not json"]})
    assert g.parse_listing("x") is None


def test_letter_prompt_has_placeholders_and_no_names(env):
    seen = {}
    c = env.install({"gemini-3-flash": ["Dear [Landlord name], ... [Tenant name]"]})
    orig = c.models.generate_content
    c.models.generate_content = lambda model, contents, config: (seen.setdefault("p", contents), orig(model, contents, config))[1]
    assert g.draft_letter(CHECK, "1 Main St")
    assert "[Tenant name]" in seen["p"] and "[Landlord name]" in seen["p"]


def test_no_key_no_crash(env, monkeypatch):
    g._reset_state()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(g, "_get_client", lambda: (_ for _ in ()).throw(RuntimeError("no key")))
    assert g.explain_verdict(CHECK, "en") is None
    assert g.zip_summary("92101", "starter", []) is None
