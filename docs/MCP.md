# RentOrKnot MCP server

An MCP server lets an assistant (Claude, for example) run RentOrKnot's checks and hand back a link that opens the
matching form already filled in. It is read-only: the tools call our own engines in-process, store nothing (a rent
check run here is not saved), and never post, message or submit anything to another site. Opening a link only fills
fields; the person presses submit.

## Connect

```
claude mcp add --transport http rentorknot https://rentorknot.us/api/mcp
```

Streamable HTTP, stateless, JSON responses, no sign-in. Locally: `http://localhost:8003/mcp` (the API serves
`/mcp`; Caddy strips `/api`, so `/api/mcp` must reach the API container like the other `/api/*` paths).

## Limits

- Request body at most 32 KB (413 above that).
- 30 tool calls a minute per client IP, 150 a minute overall (429 with `Retry-After: 60`). `initialize` and
  `tools/list` are not counted. The client IP is the last `X-Forwarded-For` entry (the one Caddy appended); earlier
  entries are client-supplied and ignored.
- `zip_profile` accepts only served ZIPs (see `/zips`); the other tools use the engines' own checks.

## Tools

Every result is `{"result": ..., "form_url": ...}`. `form_url` is absolute (`https://rentorknot.us/...`) and built
only with `contracts/prefill.py` `form_url()`, which rejects any parameter not in the prefill table.

| Tool | Does | form_url |
| --- | --- | --- |
| `check_rent_increase` | AB 1482 rules engine (not stored) | `/renter?...` |
| `check_gouging` | Penal Code 396 engine | `/gouging?...` |
| `check_listing_price` | fair-rent range, label, percentile | `/renter?tab=listing&...` |
| `owner_price_position` | owner price position, AB 1482 guardrail if a tenant stays | `/owner?...` |
| `owner_reach` | share of renter profiles who would shortlist the rent | `/owner/reach?...` |
| `search_listings` | listings query (max 25) | `/find?...` |
| `find_by_needs` | plain-language matching | `/advisor?needs=...` |
| `rank_areas` | `starter` (rent budget) or `wealth` (home price) ranking | `/find?starter_budget=...` or `/buyer?...` |
| `zip_profile` | typical rent, value, forecasts, scores | `/zip/{zip}` |
| `prefill_form` | builds a link for any form from given fields; computes nothing | that form |

Yes/no/unsure inputs take `yes`, `no`, `unsure`; dates are `YYYY-MM-DD`; home type is one of
`apartment, condo, townhouse, single_family, unknown`.

## Prefill table

Source of truth: `contracts/prefill.py` (TypeScript copy in `frontend/src/lib/prefill.ts`).

| Form | Path | Parameters |
| --- | --- | --- |
| `renter` | `/renter` | address, zip, year_built, lowest, new, effective, year, type, increases, notice, corp |
| `listing` | `/renter?tab=listing` | zip, beds, asking, baths, sqft, type, text |
| `gouging` | `/gouging` | zip, beds, new, date, before |
| `owner` | `/owner` | zip, beds, target, sqft, year, type, lowest, effective, notice, corp |
| `owner_reach` | `/owner/reach` | zip, beds, ask, text |
| `buyer` | `/buyer` | budget, beds |
| `find` | `/find` | zip, beds, type, max, source, unit, sort, page, per, starter_budget, starter_beds |
| `advisor` | `/advisor` | needs, ask |

## Advisor

The site's Mastra advisor has a `prefill_form` tool too (`frontend/src/advisor/prefill.ts`): its answers show a
button such as "Open the rent check with these numbers". It is a plain link.

## Notes

`find_by_needs` and `rank_areas` may use Gemini (parsing, "why this ZIP") through `api/llm/gemini.py`, which caches
answers; the rate limits above also protect the free tier.
