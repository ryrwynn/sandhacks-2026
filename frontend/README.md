# RentWatch web (Next.js 16)

Read `AGENTS.md` and `node_modules/next/dist/docs/` before changing anything: this is not the Next.js you know.

## Pages

`/` (mode picker and ZIP map), `/renter` (3 tabs), `/renter/letter/[id]`, `/buyer`, `/owner`, `/zip/[zip]`, `/about`.
The older `/find`, `/saved`, `/alerts` pages are kept as they were.

## API and mocks

- Browser calls go to relative `/api/...`. In production Caddy routes `/api/*` to FastAPI with the prefix stripped.
  Locally, `next.config.ts` rewrites `/api/:path*` to `${API_INTERNAL_URL || "http://localhost:8000"}/:path*`
  (the rewrite target is fixed at build time).
- Server-side fetches use `API_INTERNAL_URL` (for example `http://api:8000` in Docker), read at request time, with no `/api` prefix.
- If the API is unreachable (or answers with an error) the contract fixtures in `src/mocks/` are served instead and a
  "Showing sample data" banner appears. Set `NEXT_PUBLIC_USE_MOCKS=true` (build time) to force fixtures in the browser.
  `npm run build` needs no API and no `.env`.
- All contract calls are named functions in `src/lib/api.ts`; types are in `src/lib/contract.ts`
  (hand-written from `contracts/api_models.py`, to be replaced by `api.generated.ts`).
  `NEXT_PUBLIC_USE_API` still controls only the older `getMarket`, `getListings` and `getListingsByIds`.

## Map

`ZipMap` uses `react-map-gl/mapbox`. The token is `MAP_BOX_API_KEY`, read on the server at request time
(`src/lib/server.ts`) and passed down as a prop. If it is missing or does not start with `pk.`, ZIPs show as a
ranked list. ZIP shapes are `public/zips.geojson` (Census 2020 ZCTA polygons, simplified, property `zip`).

## Checks

`npx tsc --noEmit && npm run build`
