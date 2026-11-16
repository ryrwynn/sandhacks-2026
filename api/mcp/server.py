"""The MCP server object, its guarded ASGI app and the lifespan hook for FastAPI (api/main.py)."""
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from api.mcp import tools

MAX_BODY_BYTES = 32 * 1024     # a tool call is a few hundred bytes; pasted listing text is the largest input
CALLS_PER_MINUTE = 30          # per client IP, tools/call only (initialize and tools/list are free)
GLOBAL_CALLS_PER_MINUTE = 150  # all clients together: a backstop for the Gemini free tier and the 1 GB server

INSTRUCTIONS = (
    "RentOrKnot analyzes California rents. These tools read our own data and rules engines; they store nothing "
    "and never post or submit anything anywhere. Verdicts come from the rules engine: quote them as returned. "
    "Every result has a form_url: offer it to the user as a link that opens the site's form with the numbers "
    "filled in (the user presses the button themselves).")
TOOLS = {"check_rent_increase": tools.check_rent_increase, "check_gouging": tools.check_gouging,
         "check_listing_price": tools.check_listing_price, "owner_price_position": tools.owner_price_position,
         "owner_reach": tools.owner_reach_tool, "search_listings": tools.search_listings,
         "find_by_needs": tools.find_by_needs, "rank_areas": tools.rank_areas, "zip_profile": tools.zip_profile,
         "prefill_form": tools.prefill_form}


def make_server() -> MCPServer:
    server = MCPServer("rentorknot", title="RentOrKnot", instructions=INSTRUCTIONS)
    for name, fn in TOOLS.items():
        server.add_tool(fn, name=name, annotations={"readOnlyHint": True, "openWorldHint": False})
    return server


class _Window:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, now: float) -> bool:
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if not q:
            self.hits.pop(key, None)
            q = self.hits[key]
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def client_ip(scope) -> str:
    """The caller's IP. Caddy appends the connecting address to X-Forwarded-For, so the LAST entry is the one our
    proxy saw; earlier entries are whatever the client claimed and are ignored."""
    for k, v in scope.get("headers", []):
        if k == b"x-forwarded-for":
            parts = [p.strip() for p in v.decode("latin-1").split(",") if p.strip()]
            if parts:
                return parts[-1]
    client = scope.get("client")
    return client[0] if client else "unknown"


def _is_tool_call(body: bytes) -> bool:
    try:
        msg = json.loads(body)
    except ValueError:
        return False
    msgs = msg if isinstance(msg, list) else [msg]
    return any(isinstance(m, dict) and m.get("method") == "tools/call" for m in msgs)


class Guard:
    """ASGI middleware: request size limit and rate limits. Wraps the MCP app."""

    def __init__(self, app, per_ip: int = CALLS_PER_MINUTE, overall: int = GLOBAL_CALLS_PER_MINUTE,
                 max_body: int = MAX_BODY_BYTES, clock=time.monotonic):
        self.app, self.per_ip, self.overall, self.max_body, self.clock = app, per_ip, overall, max_body, clock
        self.ips, self.all = _Window(), _Window()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            m = await receive()
            if m["type"] == "http.disconnect":
                return
            size += len(m.get("body", b""))
            if size > self.max_body:
                return await _reject(send, 413, "Request too large")
            chunks.append(m.get("body", b""))
            if not m.get("more_body"):
                break
        body = b"".join(chunks)
        if _is_tool_call(body):
            now = self.clock()
            if not (self.ips.allow(client_ip(scope), self.per_ip, now) and self.all.allow("*", self.overall, now)):
                return await _reject(send, 429, "Rate limit: too many tool calls, try again in a minute", retry=60)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


async def _reject(send, status: int, message: str, retry: int | None = None):
    headers = [(b"content-type", b"application/json")]
    if retry:
        headers.append((b"retry-after", str(retry).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body",
                "body": json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": message}}).encode()})


def build_app(**guard_kw):
    """(guarded ASGI app, lifespan context manager). Stateless JSON responses: no session memory to leak.
    The Starlette app's own lifespan does not run when mounted, so FastAPI's lifespan must enter `lifespan`."""
    server = make_server()   # a session manager can run only once, so each app gets its own server
    # Public, read-only, no auth, behind Caddy: the Host is rentorknot.us, so the localhost-only DNS rebinding
    # allow-list would reject every real request.
    inner = server.streamable_http_app(
        streamable_http_path="/mcp", json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        max_request_body_size=MAX_BODY_BYTES)

    @asynccontextmanager
    async def lifespan():
        async with server.session_manager.run():
            yield

    return Guard(inner, **guard_kw), lifespan
