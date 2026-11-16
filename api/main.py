"""RentOrKnot API (lane D). Caddy strips /api, so routes are served at /health, /zips, ... and docs at /api/docs."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.mcp.server import build_app as build_mcp

from api.routers import (account, checks, coverage, forecasts, geo, gouging, health, listings, match, neighborhoods,
                         owner, owner_reach, tracker, trends, zips)

mcp_app, mcp_lifespan = build_mcp()


@asynccontextmanager
async def lifespan(_app):
    async with mcp_lifespan():   # the mounted MCP app's own lifespan never runs; this starts its session manager
        yield


app = FastAPI(title="RentOrKnot API", version="0.2.0", root_path="/api", lifespan=lifespan)

# gouging before checks and trends before zips/listings is not required (no path overlaps), but keeps
# the fixed paths ahead of the {id} ones.
for module in (health, gouging, trends, zips, checks, listings, neighborhoods, owner, owner_reach, tracker,
               coverage, geo, forecasts, match, account):
    app.include_router(module.router)
app.mount("/", mcp_app)   # MCP at /mcp (public https://rentorknot.us/api/mcp); last, so every route above wins
