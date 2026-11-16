#!/usr/bin/env python3
"""MCP client check (docs/SPRINT.md, "Checks before go"): list the tools, call each one, open each form_url.

Usage: uv run python scripts/mcp-check.py [MCP_URL] [WEB_BASE]
       defaults http://localhost:8000/mcp and http://localhost:3000; live: https://rentorknot.us/api/mcp https://rentorknot.us
Read-only: the tools call RentOrKnot's own engine; checks are not stored. 10 calls, under the 30-a-minute limit.
"""
import asyncio
import json
import sys
import urllib.request
from urllib.parse import urlsplit

from mcp.client import Client

MCP_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
WEB = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:3000").rstrip("/")

CALLS = {
    "check_rent_increase": {"lowest_rent_12mo": 2000, "new_rent": 2300, "effective_date": "2026-12-01", "zip": "92104"},
    "check_gouging": {"new_rent": 2600, "offer_date": "2026-11-01", "zip": "92104", "beds": 1},
    "check_listing_price": {"zip": "92104", "beds": 1, "asking_rent": 2400},
    "owner_price_position": {"zip": "92104", "beds": 2, "target_rent": 3100},
    "owner_reach": {"zip": "92104", "beds": 1, "target_rent": 2300},
    "search_listings": {"zip": "92104", "beds": 1},
    "find_by_needs": {"needs": "quiet 1 bedroom near transit under 2500"},
    "rank_areas": {"persona": "starter", "budget_usd": 2600, "beds": 1},
    "zip_profile": {"zip": "92104"},
    "prefill_form": {"form": "gouging", "values": {"zip": "92104", "new": 2600}},
}


def open_link(url: str) -> int:
    parts = urlsplit(url)
    target = WEB + parts.path + (f"?{parts.query}" if parts.query else "")
    try:
        with urllib.request.urlopen(target, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


async def main() -> int:
    bad = 0
    async with Client(MCP_URL) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        print(f"tools/list: {len(tools)} tools")
        missing = set(CALLS) - tools
        if missing:
            print(f"FAIL missing tools: {sorted(missing)}")
            bad += 1
        for name, args in CALLS.items():
            if name not in tools:
                continue
            r = await c.call_tool(name, args)
            if r.is_error:
                print(f"FAIL {name}: {r.content[0].text[:200]}")
                bad += 1
                continue
            out = r.structured_content or json.loads(r.content[0].text)
            url = out.get("form_url")
            status = open_link(url) if url else None
            ok = bool(url) and status == 200
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {name}: form_url {url} -> {status}")
    print(f"{len(CALLS) - bad}/{len(CALLS)} MCP tools passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
