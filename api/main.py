"""RentWatch API (lane D). Caddy strips /api, so routes are served at /health, /zips, ... and docs at /api/docs."""
from fastapi import FastAPI

from api.routers import checks, health, listings, neighborhoods, owner, zips

app = FastAPI(title="RentWatch API", version="0.1.0", root_path="/api")

for module in (health, zips, checks, listings, neighborhoods, owner):
    app.include_router(module.router)
