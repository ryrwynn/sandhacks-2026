"""RentOrKnot API (lane D). Caddy strips /api, so routes are served at /health, /zips, ... and docs at /api/docs."""
from fastapi import FastAPI

from api.routers import (account, checks, coverage, forecasts, geo, gouging, health, listings, match, neighborhoods,
                         owner, owner_reach, tracker, trends, zips)

app = FastAPI(title="RentOrKnot API", version="0.2.0", root_path="/api")

# gouging before checks and trends before zips/listings is not required (no path overlaps), but keeps
# the fixed paths ahead of the {id} ones.
for module in (health, gouging, trends, zips, checks, listings, neighborhoods, owner, owner_reach, tracker,
               coverage, geo, forecasts, match, account):
    app.include_router(module.router)
