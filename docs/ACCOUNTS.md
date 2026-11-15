# Accounts: where saved apartments live

## Recommendation

Keep **local-only saving as the default** and ship **optional Google sign-in behind a flag** (built, off until the keys are set). Do not build the anonymous sync code. Local saving is private by construction, works with no keys, and cannot break the demo. Google sign-in adds the one thing local saving cannot do (the same watchlist on a phone and a laptop) and is a visible, judgeable feature, but it stays off the critical path: with the flag off the site behaves exactly as before, and with it on, a failed sign-in or a down API leaves local saving untouched.

## Comparison

| | Local-only (today) | Anonymous sync code | Google sign-in (optional) |
| --- | --- | --- | --- |
| Privacy | Best. Nothing leaves the browser. | Good. Server holds saves keyed by a random code; no identity. | Good if built as specified: server stores only a hash of Google's subject ID and the saves. No email, name or photo is kept (the JWT is stripped to the subject). Google still learns the user visited. |
| Security | Nothing to attack server-side. Cleared storage loses the list. | The code is a bearer secret: anyone who sees it owns the list; users paste it into chat and screenshots. Needs rate limits against guessing. | Google handles authentication. Risks: leaked `AUTH_SECRET` (can forge sessions and recompute hashes), and the Next.js-to-API token (`ACCOUNT_API_TOKEN`). Mitigated: only the Next.js server calls the API, and the subject hash is salted with `AUTH_SECRET`. |
| Effort | Done. | Low to medium: code generation, lookup, rate limiting, a "lost code" story with no recovery. | Medium. Needs Google OAuth client, redirect URIs, Auth.js, a small API and merge logic. Built tonight. |
| Demo risk | None. | Low, but the UX (copy a code) is awkward to demo. | Highest of the three: depends on Google's consent screen, redirect URIs matching exactly, and test-user settings while the OAuth app is in "Testing" mode. Contained by the flag and by keeping local saving as the fallback. |
| Judging value | Neutral; matches the "no accounts, no tracking" story. | Low: reads as a workaround. | Highest: real cross-device sync with a privacy-first design (hashed subject, no PII) is a talking point. |

## What is built (flag off by default)

- Sign-in turns on only when `AUTH_SECRET` and a Google client ID (`GOOGLE_CLIENT_ID`, or `AUTH_GOOGLE_ID`) are set at runtime. Otherwise `/auth/*` answers 404 and `<AccountButton/>` renders nothing.
- Auth.js v5 (`next-auth@5.0.0-beta.32`) with `basePath: "/auth"` (confirmed in the installed `@auth/core` types: the default is `/api/auth` for `next-auth`, so it must be set explicitly), JWT sessions, Google provider. The JWT is reduced to the Google subject ID; email, name and picture are dropped in the profile and jwt callbacks.
- Saves live in the `user_saves` table keyed by `subject_hash = sha256(AUTH_SECRET + sub)`. Only the Next.js server calls `GET/PUT /account/saves` on FastAPI, sending `X-Account-Token` (`ACCOUNT_API_TOKEN`) and `X-Subject-Hash`. The browser reaches saves through `/auth/saves` (a Next.js route, not `/api`, because Caddy sends `/api/*` to FastAPI). With `ACCOUNT_API_TOKEN` unset the API returns 404.
- Merge: on sign-in the browser's local saves are unioned with the server's (newest data wins per listing) and written both ways. A listing removed locally after a sync is removed on the server too. Example apartments seeded on a first visit are never uploaded.

## Known limits

- Removing a save on one device and re-adding it elsewhere before the first device syncs can bring it back (last write wins; there are no tombstones).
- Rotating `AUTH_SECRET` signs everyone out and changes every subject hash, so server saves become unreachable. Treat it as permanent.
- Sync runs while a tab is open (on load and every few seconds); it is not push-based.

## Redirect URIs to register (Google Cloud Console, OAuth web client)

- `https://rentorknot.us/auth/callback/google`
- `http://localhost:3000/auth/callback/google` (local test)
- Authorized JavaScript origins: `https://rentorknot.us`, `http://localhost:3000`

## Environment variables

| Name | Where | Meaning |
| --- | --- | --- |
| `GOOGLE_CLIENT_ID` (or `AUTH_GOOGLE_ID`) | frontend | Turns sign-in on together with `AUTH_SECRET` |
| `GOOGLE_CLIENT_SECRET` (or `AUTH_GOOGLE_SECRET`) | frontend | OAuth client secret |
| `AUTH_SECRET` | frontend | Signs JWTs and salts the subject hash |
| `ACCOUNT_API_TOKEN` | frontend and API (same value) | Shared secret for the Next.js-to-FastAPI call; unset on the API means the feature is off |
| `AUTH_URL` | frontend, optional | `https://rentorknot.us` (origin only; the base path is set in code) |
| `API_INTERNAL_URL` | frontend | Existing; where the Next.js server reaches FastAPI |

Auth.js trusts the proxy host (`trustHost: true`), so `AUTH_TRUST_HOST` is not needed.

## Manual test (needs a real Google sign-in; not possible unattended)

1. Create the OAuth client with the URIs above; set the env vars on the frontend and API containers; rebuild.
2. Flag off check: unset `GOOGLE_CLIENT_ID`; `/auth/session` returns 404 and no account button appears.
3. Flag on: the account button shows "Sign in". Click it, pick a Google account, and return to the site; the button shows "Signed in".
4. In browser dev tools, `/auth/session` must contain no email or name, only an expiry.
5. Save two apartments while signed out, then sign in: they stay, and the `user_saves` table has two rows whose `subject_hash` is 64 hex characters (no email anywhere).
6. Open the site in a second browser, sign in with the same account: the two saves appear after a few seconds. Remove one there; after a few seconds it is gone from the first browser too.
7. Sign out: saves remain locally; the account button shows "Sign in" again.
8. With `ACCOUNT_API_TOKEN` wrong on the frontend, saves keep working locally and the button stays quiet.
