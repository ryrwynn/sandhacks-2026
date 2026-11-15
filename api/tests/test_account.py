"""Account saves endpoints. No database: _load and _store are replaced by an in-memory dict."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import db
from api.main import app
from api.routers import account
from contracts.api_models import AccountSavesResponse, PutSavesRequest, SavedItem

F = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
client = TestClient(app)
H = "a" * 64
OK = {"X-Account-Token": "tok", "X-Subject-Hash": H}


@pytest.fixture(autouse=True)
def mem(monkeypatch):
    monkeypatch.setenv("ACCOUNT_API_TOKEN", "tok")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store: dict[str, dict[int, SavedItem]] = {}
    monkeypatch.setattr(account, "_load",
                        lambda h: sorted(store.get(h, {}).values(), key=lambda s: s.saved_at, reverse=True))

    def _store(h, items, replace):
        d = store.setdefault(h, {})
        if replace:
            d.clear()
        for i in items:
            d[i.listing_id] = i
    monkeypatch.setattr(account, "_store", _store)
    return store


def item(i, day=1, price=2000.0, target=None):
    return {"listing_id": i, "saved_at": datetime(2026, 11, day, tzinfo=timezone.utc).isoformat(),
            "price_at_save": price, "target": target}


def test_off_without_token_env(monkeypatch):
    monkeypatch.delenv("ACCOUNT_API_TOKEN")
    assert client.get("/account/saves", headers=OK).status_code == 404
    assert client.put("/account/saves", headers=OK, json={"items": []}).status_code == 404


def test_wrong_or_missing_token_is_401():
    assert client.get("/account/saves", headers={"X-Subject-Hash": H}).status_code == 401
    assert client.get("/account/saves", headers={**OK, "X-Account-Token": "nope"}).status_code == 401


def test_bad_subject_hash_is_400():
    for bad in (None, "user@example.com", "A" * 64, "a" * 63):
        h = {"X-Account-Token": "tok"}
        if bad is not None:
            h["X-Subject-Hash"] = bad
        assert client.get("/account/saves", headers=h).status_code == 400


def test_empty_get():
    r = client.get("/account/saves", headers=OK)
    assert r.status_code == 200 and r.json() == {"items": []}


def test_fixture_roundtrip_matches_contract():
    body = json.loads((F / "requests" / "account_saves.json").read_text())
    PutSavesRequest.model_validate(body)
    r = client.put("/account/saves", headers=OK, json=body)
    assert r.status_code == 200
    AccountSavesResponse.model_validate(r.json())
    assert len(r.json()["items"]) == len(body["items"])


def test_merge_unions_and_keeps_older_saved_at():
    client.put("/account/saves", headers=OK, json={"items": [item(1, day=5), item(2, day=6)]})
    r = client.put("/account/saves", headers=OK,
                   json={"items": [item(2, day=9, target=1800), item(3, day=7)], "merge": True})
    got = {i["listing_id"]: i for i in r.json()["items"]}
    assert set(got) == {1, 2, 3}
    assert got[2]["target"] == 1800 and got[2]["saved_at"].startswith("2026-11-06")


def test_replace_drops_missing():
    client.put("/account/saves", headers=OK, json={"items": [item(1), item(2)]})
    r = client.put("/account/saves", headers=OK, json={"items": [item(2)], "merge": False})
    assert [i["listing_id"] for i in r.json()["items"]] == [2]


def test_users_are_isolated():
    client.put("/account/saves", headers=OK, json={"items": [item(1)]})
    other = {**OK, "X-Subject-Hash": "b" * 64}
    assert client.get("/account/saves", headers=other).json() == {"items": []}


def test_too_many_items():
    r = client.put("/account/saves", headers=OK, json={"items": [item(i) for i in range(account.MAX_ITEMS + 1)]})
    assert r.status_code == 413


def test_db_down_is_503(monkeypatch):
    def boom(h):
        raise db.DBUnavailable("down")
    monkeypatch.setattr(account, "_load", boom)
    assert client.get("/account/saves", headers=OK).status_code == 503
