// The only file that talks to the advisor. The /advisor page calls askAdvisor(messages) and renders streamed
// text. night-match's client replaces the body of askAdvisor at merge; keep the signature.
import { markMock } from "./mockflag";

export type AdvisorMessage = { role: "user" | "assistant"; content: string };

const SAMPLE =
  "This is a sample answer: the housing advisor is not connected yet. When it is, it will use RentOrKnot's own data (asking rents, forecasts, the AB 1482 cap and the gouging rules) and will say which figures it used. It cannot give legal advice.";

async function* sample(): AsyncGenerator<string> {
  markMock();
  for (const w of SAMPLE.split(" ")) {
    yield w + " ";
    await new Promise((r) => setTimeout(r, 25));
  }
}

/** POST /advisor/chat with the conversation; yields text chunks as they stream in. Falls back to a labeled sample. */
export async function* askAdvisor(messages: AdvisorMessage[], signal?: AbortSignal): AsyncGenerator<string> {
  if (process.env.NEXT_PUBLIC_USE_MOCKS === "true") return yield* sample();
  let res: Response;
  try {
    res = await fetch("/advisor/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
      signal,
    });
  } catch {
    if (signal?.aborted) return;
    return yield* sample();
  }
  if (!res.ok || !res.body) return yield* sample();   // 404/501: not built yet
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const t = dec.decode(value, { stream: true });
    if (t) yield t;
  }
}
