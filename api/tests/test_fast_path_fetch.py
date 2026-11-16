"""Sprint D1 fetch side: batching, budget refusal, concurrent polling and streamed gzip NDJSON (local server, no Bright Data)."""
import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from worker import bd, sprint


def test_split_groups_of_about_fifteen():
    inputs = [{"url": str(i)} for i in range(104)]
    g = sprint.split(inputs)
    assert sum(len(x) for x in g) == 104 and max(len(x) for x in g) <= 15 and len(g) == 7
    assert sprint.split(inputs[:3]) == [inputs[:3]]


class FakeConn:
    def __init__(self, spent):
        self.spent = spent

    def execute(self, sql, args=()):
        class R:
            def __init__(s, rows):
                s.rows = rows

            def fetchone(s):
                return s.rows[0]

            def fetchall(s):
                return s.rows
        if "sum(est_usd)" in sql:
            return R([(self.spent,)])
        return R([])


def test_trigger_refused_before_the_first_call_when_it_would_pass_the_sprint_budget(monkeypatch):
    monkeypatch.setenv("SPRINT_BUDGET_USD", "40")
    t = {"source_key": "zillow_rent_county", "fetch": {"dataset_id": "x"}}
    inputs = [{"url": f"u{i}"} for i in range(30)]

    class NoTrigger:
        def trigger(self, *a, **k):
            raise AssertionError("must not trigger")
    # 30 ZIPs x limit 10 x ratio 15 = 4,500 records = $6.75
    with pytest.raises(bd.BudgetExceeded):
        sprint.plan_and_trigger(FakeConn(35.0), t, inputs, 10, note="t", client=NoTrigger())
    plan = sprint.plan_and_trigger(FakeConn(0.0), t, inputs, 10, note="t", client=NoTrigger(), dry_run=True)
    assert sum(p["est_usd"] for p in plan) == pytest.approx(6.75, abs=0.05) and len(plan) == 2


class Handler(BaseHTTPRequestHandler):
    body = b"".join(json.dumps({"zpid": i}).encode() + b"\n" for i in range(5000))

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = json.dumps({"status": "ready"}).encode() if "/progress/" in self.path else gzip.compress(self.body)
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def test_concurrent_streamed_gzip_download_and_follow(monkeypatch, tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(sprint, "API", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(sprint, "CACHE", tmp_path)
    monkeypatch.setenv("BRIGHTDATA_API_TOKEN", "test-token")
    ds = sprint.start_downloads(["a", "b"])
    got = [sum(1 for _ in sprint.follow(d)) for d in ds]
    srv.shutdown()
    assert got == [5000, 5000] and all(d.error is None for d in ds)


def test_county_zip_form_urls():
    from worker.mapping import load_template
    got = bd.zillow_zip_inputs(load_template("zillow_rent_county"), ["92004", "92129"])
    assert [g["url"] for g in got] == ["https://www.zillow.com/homes/for_rent/92004_rb/",
                                       "https://www.zillow.com/homes/for_rent/92129_rb/"]
