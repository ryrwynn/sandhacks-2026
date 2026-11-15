// The only file that talks to the advisor. The /advisor page calls askAdvisor(messages) and renders streamed
// text. night-match's client replaces the body of askAdvisor at merge; keep the signature.
import { askAdvisor as askMatchAdvisor } from "@/advisor/client";
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

/** Asks the advisor (night-match's JSON client: POST /advisor/chat {text}) and yields the answer. The advisor is
 * stateless, so the latest user message is sent, with the previous turn as context. Falls back to a labeled sample. */
export async function* askAdvisor(messages: AdvisorMessage[], signal?: AbortSignal): AsyncGenerator<string> {
  if (process.env.NEXT_PUBLIC_USE_MOCKS === "true") return yield* sample();
  const users = messages.filter((m) => m.role === "user");
  const last = users[users.length - 1]?.content ?? "";
  const prev = users.length > 1 ? users[users.length - 2].content : "";
  const text = (prev ? `Earlier I asked: ${prev}\nNow: ${last}` : last).slice(0, 1900);
  try {
    const res = await askMatchAdvisor(text, signal);
    yield res.answer;
  } catch {
    if (signal?.aborted) return;
    return yield* sample();   // 404/501 or network error: not connected
  }
}
