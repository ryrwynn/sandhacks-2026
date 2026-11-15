# Auth.js (optional Google sign-in): reference for RentOrKnot

Sources: Auth.js docs at authjs.dev (installation, deployment, Google provider pages, read 2026-11-15, paraphrased), and NIGHT.md's Accounts spec. Sign-in is optional and behind a flag; local-first saving stays the default.

## Packages (exact npm names; versions on npm 2026-11-15)
| Package | Version on npm | Note |
| --- | --- | --- |
| `next-auth@beta` | 5.0.0-beta.32 | Auth.js v5 for Next.js. Use this tag, not `latest`. |
| `next-auth@latest` | 4.24.15 | v4 (Pages-era). Do not use. |
| `@auth/core` | 0.41.3 | Installed for you by next-auth; do not install directly. |

Install with `npm install next-auth@beta`. Record the exact resolved version in `DECISIONS.md`.

## Required environment variables
Names are read from the environment. Never print or commit values; never put them in `.env` reads from code (read `process.env` only).
- `AUTH_SECRET`: the only mandatory variable. Generate with `npx auth secret`. Used to encode JWTs.
- `AUTH_GOOGLE_ID`: Google OAuth client ID.
- `AUTH_GOOGLE_SECRET`: Google OAuth client secret.
- `AUTH_URL`: needed when the app is served under a base path. Example in the docs: `AUTH_URL=http://localhost:3000/web/auth`.
- `AUTH_TRUST_HOST=true`: needed behind a reverse proxy (Caddy here). Without it, Auth.js will not trust `X-Forwarded-Host`. Auth.js also accepts `trustHost: true` in config.

NIGHT.md turns sign-in on only when `GOOGLE_CLIENT_ID` and `AUTH_SECRET` exist. Map `GOOGLE_CLIENT_ID` to `AUTH_GOOGLE_ID` in one place (the config), and read both names from the environment only.

## Google provider
```ts
import NextAuth from 'next-auth'
import Google from 'next-auth/providers/google'

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  basePath: '/auth',
  session: { strategy: 'jwt' },
})
```
The `basePath` and `session` options come from NIGHT.md and are not confirmed on the docs page read; verify them on the installed beta (see Missing). Adding the subject ID to the token needs a `jwt` callback; check its shape on the installed version.
- Import path: `next-auth/providers/google`.
- Callback URL to register in Google Cloud Console (Authorized redirect URI): `https://<host>/auth/callback/google` when `basePath` is `/auth`. The docs show `/api/auth/callback/google` for the default base path.
- Default scopes and returned profile fields are not documented on the page read. The OAuth profile includes `email_verified`, which can be checked in a `signIn` callback.

## Base path and Caddy routing (this project)
- NIGHT.md sets `basePath: "/auth"`, **not** `/api/auth`, because Caddy sends `/api/*` to FastAPI.
- Route handlers live at `app/auth/[...nextauth]/route.ts` and export `handlers`:
  ```ts
  export const { GET, POST } = handlers
  ```
- The public URL the browser uses must match `AUTH_URL` and the Google redirect URI.

## Sessions
- Use **JWT sessions** (`session: { strategy: 'jwt' }`), per NIGHT.md. No database adapter is needed.
- `AUTH_SECRET` signs the JWT. Rotating it signs every user out.
- The session holds only the Google subject ID (`sub`). **Do not store email or name.**

## Server-side saves (NIGHT.md)
- Key saved data by a hash of the Google subject ID only, for example `sha256(sub + server_salt)`. The salt is an env var (name chosen by the lane; never committed).
- Local saves merge into the server copy on first sign-in.
- Sign-in stays off unless `GOOGLE_CLIENT_ID` and `AUTH_SECRET` are set. Tests mock the provider; a real Google sign-in needs a manual check on the morning list.

## Reading the session (server)
Call `auth()` (exported from the NextAuth config) in a server route. Confirm the exact session shape on the installed beta before reading the subject ID from it.

## Missing
- **`basePath` option details.** The Auth.js deployment page only mentions `AUTH_URL` for a non-root path. The `basePath: "/auth"` option is taken from NIGHT.md and must be verified on the installed `next-auth@beta`. Fallback: set `AUTH_URL` to `https://<host>/auth` and test that `/auth/session` responds.
- **Google default scopes and profile fields** (`sub`, `email`, `name`). Fallback: the provider's default profile; read only `sub` and use it as the hashed key.
- **Session strategy default for v5 beta and the exact `auth()` return type.** Fallback: check the installed type definitions and keep the session to `sub` only.
- **Our Google OAuth client settings** (redirect URIs, consent screen). Not in `raw/` (`raw/google-auth/` was absent). Fallback: sign-in stays off; note the redirect URI in `MORNING.md` for the team to set by hand.
- **Real sign-in test.** Cannot run unattended. Fallback: mock the provider in tests; list a manual sign-in check for the morning.
