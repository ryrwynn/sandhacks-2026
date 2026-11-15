# Mastra: reference for RentOrKnot

Sources: `docs/reference/raw/mastra/public-docs-notes.md` (read 2026-11-15, paraphrased), mastra.ai/llms.txt, and the docs pages it links. Mastra docs use `@latest` tags, not pinned versions.

## Packages (exact npm names; versions = npm `latest` on 2026-11-15)
| Package | Latest | Use |
| --- | --- | --- |
| `@mastra/core` | 1.83.0 | Agents, tools, workflows, Mastra class (required) |
| `zod` | 4.6.7 (`zod@^4`) | Tool input schemas (required) |
| `@mastra/memory` | 1.41.1 | Per-user memory |
| `@mastra/pg` | 1.36.0 | `PostgresStore` for memory and storage |
| `@mastra/ai-sdk` | 1.12.0 | `handleChatStream` for streaming to the UI |
| `ai` | 7.0.173 | `createUIMessageStreamResponse` (pair with `@mastra/ai-sdk`) |
| `@mastra/evals` | 1.10.11 | Prebuilt scorers |
| `@mastra/mcp` | 2.9.0 | MCP client and server (optional) |
| `mastra` (dev) | use `npx mastra@latest` | CLI and Studio |

Check the versions before installing (`npm view @mastra/core version`). Pin the exact versions in `frontend/package.json` after the first install, and record them in `DECISIONS.md`.

- Node **22.13+**. `docker/web.Dockerfile` uses node:22-slim; confirm the exact version on build.
- Install: `npm install @mastra/core@1.83.0 zod@^4` and only what you use.
- Scaffold (optional): `npx mastra@latest init` creates `src/mastra/` with an agent, a tool and `index.ts`.
- tsconfig: `module` and `moduleResolution` set to ES2022 / bundler.
- **`next.config.ts` needs `serverExternalPackages: ['@mastra/*']`.**

## Agent
```ts
import { Agent } from '@mastra/core/agent'

export const advisor = new Agent({
  id: 'housing-advisor',
  name: 'Housing Advisor',
  instructions: 'Use the tools for every number. Never invent listings.',
  model: { id: 'google/gemini-3.5-flash-lite', apiKey: process.env.GEMINI_API_KEY },
  tools: { searchListings, rankByNeeds },
})

const res = await advisor.generate(text, { maxSteps: 4 })
```
- Model IDs use `provider/model` with a slash.
- Without an explicit `apiKey`, Mastra reads `GOOGLE_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY`. Pass `apiKey: process.env.GEMINI_API_KEY` explicitly.
- Gemini options go in `providerOptions.google`, for example `thinkingConfig: { thinkingLevel: 'minimal' }` (see `gemini.md` for which levels each model accepts).
- `maxSteps` goes on `generate` or `stream` (default 5). `stopWhen` is also accepted. Whether `defaultOptions` accepts `maxSteps` is UNVERIFIED.
- Results carry `text`, `toolCalls`, `toolResults`, `steps`, `usage`, `finishReason`.
- Register agents: `new Mastra({ agents: { advisor } })`.

## Tools
```ts
import { createTool } from '@mastra/core/tools'
import { z } from 'zod'

export const searchListings = createTool({
  id: 'search-listings',
  description: 'Search RentOrKnot listings by ZIP and budget',
  inputSchema: z.object({ zip: z.string(), maxRent: z.number() }),
  execute: async (input, { abortSignal }) => {
    const r = await fetch(`${process.env.API_INTERNAL_URL}/listings?zip=${input.zip}`,
      { signal: abortSignal })
    return await r.json()
  },
})
```
- Use `createTool` from `@mastra/core/tools`. **Plain objects fail silently.**
- Pass `abortSignal` to `fetch`.
- The built-in `webFetchTool` blocks localhost and private IPs. Write our own HTTP tools for the FastAPI backend.
- `toModelOutput` can shrink what the model sees (use it to cut large API responses).
- `API_INTERNAL_URL` is a placeholder name; use the env var the app already defines.

## Workflows
- Build with `createStep` and `createWorkflow`. Chain with `.then`, `.parallel`, `.branch`, `.map`, `.foreach`, `.dountil`, then `.commit()`.
- Run: `const run = await wf.createRun(); const out = await run.start({ inputData })`.
- Branch conditions all run if true, so make them mutually exclusive.

## Next.js
The docs' Next guide calls the agent from a route handler on the Node runtime:
```ts
import { handleChatStream } from '@mastra/ai-sdk'
import { createUIMessageStreamResponse } from 'ai'

const stream = await handleChatStream({ mastra, agentId: 'housing-advisor', version: 'v7', params })
return createUIMessageStreamResponse({ stream })
```
- **Route path: use `/advisor/chat`, not `/api/chat`.** Caddy sends `/api/*` to FastAPI.
- Run on the Node runtime (not edge).
- Do **not** run `mastra build` plus a separate server (port 4111) here. The server has 1 GB of RAM.

## Memory and storage
```ts
import { Memory } from '@mastra/memory'
import { PostgresStore } from '@mastra/pg'

const memory = new Memory({ options: { lastMessages: 20 } })
// per call:
await advisor.generate(text, { memory: { resource: userId, thread: threadId }, maxSteps: 4 })
```
- Take `resource` (the user ID) from the server session, never from the request body.
- Storage: `PostgresStore({ id, connectionString })` from `@mastra/pg`. Other stores (LibSQL, MongoDB) exist; LibSQL is file-based and local-only.
- Tonight: keep the advisor stateless, or use Postgres in its own schema. **No local file database in Docker.**
- Observational memory needs an adapter that supports it.

## Evals
- `@mastra/evals` ships scorers such as `createAnswerRelevancyScorer({ model })` and `checks.calledTool('name')`.
- Attach them to agents with sampling. Model-graded scorers cost model calls, so count them against the Gemini daily cap.

## MCP (optional)
- `MCPClient` (servers by URL or stdio) and `MCPServer` (exposes tools, agents and workflows at `/api/mcp/:id/mcp`) from `@mastra/mcp`.
- Optional for RentOrKnot. If built, expose only read-only tools.

## Studio
- `npx mastra dev` serves Studio and REST at `localhost:4111` (chat, tool runs, traces, scorers). Local debugging only.

## Prize angle (MLH "Best Use of Mastra")
Judges want stateful, autonomous, production-grade agents and workflows. Show: a multi-step workflow (parse needs, search, rank, explain); tools over our API; per-user memory; evals or scorers; Studio for local debugging; optionally an MCP server exposing read-only tools.

## Missing
- **Exact `@mastra/core` version the docs assume.** The docs say `@latest`; npm shows 1.83.0 on 2026-11-15. Fallback: install the npm version and pin it.
- **Whether `defaultOptions` accepts `maxSteps`.** Fallback: pass `maxSteps` on each `generate` call.
- **Gemini provider page details** (the index lists no Gemini-specific page; the models page is `mastra.ai/models/providers.md`). Fallback: use `google/<model>` with `apiKey` set explicitly, and test one call with a mocked model.
- **Exact Next.js adapter signature for `handleChatStream` and `version: 'v7'`.** Fallback: check the reference page `mastra.ai/reference/server/next-adapter.md` in the build, and mock the route in tests.
- **Whether `PostgresStore` works inside the Next.js bundle** without extra config. Fallback: keep the advisor stateless; add memory only if the build passes.
- **Node version the Mastra packages require** (22.13+ is the stated minimum; the Dockerfile uses node:22-slim). Fallback: confirm on Docker build; if it fails, pin to the newest Node 22 image.
- **Observational memory adapter list.** Fallback: plain per-thread memory with `lastMessages: 20`.
