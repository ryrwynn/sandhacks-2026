"""A change in data_version clears the API's caches; a missing table or no database is ignored."""
import time

from api import db


def _reset(monkeypatch):
    monkeypatch.setitem(db._version, "checked", 0.0)
    monkeypatch.setitem(db._version, "seen", None)


def test_change_clears_caches_and_registered_ones(monkeypatch):
    _reset(monkeypatch)
    cleared = []
    monkeypatch.setattr(db, "_cache_clearers", [lambda: cleared.append(1)])
    versions = iter([1, 1, 2])
    monkeypatch.setattr(db, "_raw_fetch", lambda sql, params=None: [{"version": next(versions)}])
    monkeypatch.setitem(db._served_cache, "areas", {"92104": {}})
    monkeypatch.setitem(db._served_cache, "at", time.monotonic())
    for _ in range(3):
        db._version["checked"] = 0.0
        db.check_data_version()
    assert cleared == [1] and db._served_cache["areas"] == {}


def test_checked_at_most_every_30_seconds(monkeypatch):
    _reset(monkeypatch)
    n = []
    monkeypatch.setattr(db, "_raw_fetch", lambda sql, params=None: n.append(1) or [{"version": 1}])
    db.check_data_version()
    db.check_data_version()
    db.check_data_version()
    assert len(n) == 1


def test_missing_table_or_database_is_ignored(monkeypatch):
    _reset(monkeypatch)

    def boom(sql, params=None):
        raise db.DBUnavailable("relation data_version does not exist")
    monkeypatch.setattr(db, "_raw_fetch", boom)
    db.check_data_version()   # no exception
