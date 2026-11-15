# Gemini API: reference for RentOrKnot

Sources: `docs/reference/raw/gemini/public-docs-notes.md` (read 2026-11-15, paraphrased from aistudio.google.com/docs), with the project's free-tier numbers from a screenshot on that date. The docs present the Interactions API as the default and call `generate_content` legacy. The project's code uses `generate_content` and works, so do not migrate tonight.

## Hard rules (CLAUDE.md and NIGHT.md)
- Free tier only. Call Gemini **only through `api/llm/gemini.py`**, which caches answers. Tests mock the network. Never loop over real calls.
- Gemini only parses and writes words; its text must pass `figures_ok`. Verdicts come from `api/rules/ab1482.py`.
- Embeddings: at most **900 requests tonight** (the embedding quota is 1,000 a day).
- Lowest thinking level: `minimal` on the Flash-Lite models, `low` on `gemini-3.8-flash`.
- A 429 with code `quota_exceeded` is the daily cap: **do not retry**.
- Never ship a key to the browser. Restrict keys to the Gemini API.

## Free-tier limits (per project, per model; screenshot 2026-11-15)
| Model family | RPM | RPD |
| --- | --- | --- |
| Flash (for example `gemini-3.8-flash`, `gemini-3.6-flash`) | 5 | **20** |
| Flash-Lite (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`) | 15 | **500** |
| Embedding (`gemini-embedding-2`) | 100 | **1,000** |
| Gemma 4 | 30 | 14,400 (16K TPM) |

- Limits are per **project** (not per key), per model, and measured as RPM, TPM and RPD. Exceeding any one fails the request.
- RPD resets at **midnight Pacific**.
- Per-model numbers live on the logged-in AI Studio page; re-check before a long run.

## Models
- Flash, stable: `gemini-3.8-flash` (Sep 2026), `gemini-3.6-flash` (Jul 2026).
- Flash-Lite, stable: `gemini-3.5-flash-lite` (Jul 2026); `gemini-3.1-flash-lite` (May 2026; shutdown no earlier than May 2027).
- Preview: `gemini-3-flash-preview`.
- Flagship: `gemini-4-hydrogen`, `gemini-4-carbon`, `gemini-4-argon`.
- Deprecated: `gemini-2.5-flash` routes to `gemini-3.5-flash-lite` from **Dec 1, 2026**.

## Thinking (`thinking_level`)
| Model | Lowest level | Default |
| --- | --- | --- |
| `gemini-3.8-flash` | **low** (`minimal` is not supported) | medium |
| `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` | **minimal** | minimal on Flash-Lite |
| `gemini-4-hydrogen` | low | |

- Thought tokens are billed, and `max_output_tokens` includes them. Leave room.
- **Remove `temperature`, `top_p` and `top_k`** on Gemini 4 and 3.6+. They are ignored now and will return 400 later.

## Structured output
Documented pattern (Interactions API):
```python
interaction = client.interactions.create(
    model="gemini-3.5-flash-lite",
    input=prompt,
    response_format={"type": "text", "mime_type": "application/json",
                     "schema": Model.model_json_schema()},
)
data = Model.model_validate_json(interaction.output_text)
```
- Keep schemas flat. `minLength`/`maxLength` and `uniqueItems` are ignored; `minItems`/`maxItems` are enforced.
- The `generate_content` `response_schema` and `response.parsed` are not on these pages; check python-genai before relying on them.

## Retries and timeouts
- python-genai retries timeouts, network errors, 429 and 5xx by itself: up to 4 retries, about 1 s initial delay, 60 s max.
- Our own wrapper: **retry only 408, 429 `rate_limit_exceeded`/`too_many_requests`, and 5xx**. Never retry 400, 402, 403, 404, or 429 `quota_exceeded`.
- Units of the `HttpOptions` timeout are not stated; check python-genai.

## Errors
| Status | Code | Meaning | Action |
| --- | --- | --- | --- |
| 429 | `rate_limit_exceeded` | Per-minute or per-second limit | Back off |
| 429 | `too_many_requests` | Short burst | Back off |
| 429 | `quota_exceeded` | **Daily** quota | Stop; wait for midnight Pacific |
| 503 | `service_unavailable` | Overloaded | Back off |
| 500 | `api_error` | Server error | Retry with backoff |
| 504 | `deadline_exceeded` | Timeout | Retry once |
| 403 | `FREE_TIER_VERIFICATION_REQUIRED` | Account needs verification | Fix in console |

- A key reported as leaked must be replaced.
- The older google.rpc QuotaFailure JSON (`quotaId`, `retryDelay`) is not shown on these pages. Detect the daily cap by the `quota_exceeded` code alone, and check the QuotaFailure format in python-genai before relying on anything else.

## Embeddings (`gemini-embedding-2`)
- Current model. `gemini-embedding-001` shuts down May 2028.
- Default 3072 dimensions. `output_dimensionality` 128 to 3072; recommended 768, 1536 or 3072. **Use 768 for pgvector** (`vector(768)` in Tiger Data).
- **No `task_type` field.** Prefix the text instead:
  - query: `task: search result | query: {text}`
  - document: `title: {title or none} | text: {text}`
- Batch: pass several `types.Content` items to get one vector each. Several parts inside one Content produce one aggregated vector.
- Limit: 8,192 input tokens per request.

```python
res = client.models.embed_content(
    model="gemini-embedding-2",
    contents=[types.Content(parts=[types.Part.from_text(text=t)]) for t in texts],
    config=types.EmbedContentConfig(output_dimensionality=768),
)
vectors = [e.values for e in res.embeddings]
```

## Keys and SDK
- python-genai reads `GEMINI_API_KEY` or `GOOGLE_API_KEY`. **`GOOGLE_API_KEY` wins if both are set.**
- Mastra and the AI SDK read `GOOGLE_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY`. Pass `apiKey: process.env.GEMINI_API_KEY` explicitly (see `mastra.md`).
- Keys are read from the environment only. Never print them.

## Missing
- **Exact daily count used tonight** is not in the docs. Fallback: count calls in `api/llm/gemini.py`'s cache log, and stop at 20 for Flash, 500 for Flash-Lite, and 900 for embeddings.
- **`generate_content` response schema support** in python-genai (`response_schema`, `response.parsed`). Fallback: use the Interactions pattern above, or parse JSON with `model_validate_json` on the text and retry once.
- **Timeout units in `HttpOptions`.** Fallback: set the timeout in seconds and check with one mocked call.
- **Gemma 4 model ID for the API** is not listed on these pages. Fallback: do not use Gemma; use Flash-Lite.
- **Preview model lifetime** for `gemini-3-flash-preview`. Fallback: do not depend on it; use the stable IDs above.
- **Live per-model limits on our project** come from the screenshot of 2026-11-15 only. Fallback: re-check in AI Studio before a long run, and assume the lower Flash number (20 a day).
