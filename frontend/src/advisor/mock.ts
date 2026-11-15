// A scripted model for local runs and tests (ADVISOR_MOCK=1, never in production): no Gemini request is sent.
// Turn 1 calls match_listings with the user's text; turn 2 writes an answer from the tool result.
import { MockLanguageModelV3 } from "ai/test";

type Prompt = { role: string; content: unknown }[];

const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 1, text: 1, reasoning: 0 },
};

function lastUserText(prompt: Prompt): string {
  for (const m of [...prompt].reverse()) {
    if (m.role !== "user") continue;
    const c = m.content;
    if (typeof c === "string") return c;
    if (Array.isArray(c)) return c.map((p: { text?: string }) => p.text ?? "").join(" ");
  }
  return "a place to rent";
}

function plan(prompt: Prompt) {
  const toolMsg = prompt.find((m) => m.role === "tool");
  if (!toolMsg) {
    return { kind: "tool" as const, input: JSON.stringify({ text: lastUserText(prompt), limit: 3 }) };
  }
  const raw = JSON.stringify(toolMsg.content);
  const price = raw.match(/current_price_usd[^0-9]*(\d+(?:\.\d+)?)/);
  const text = price
    ? `Your best match asks $${Number(price[1]).toLocaleString("en-US")} a month. The ranking and reasons come from the match tool.`
    : "I could not find a listing that fits those filters.";
  return { kind: "text" as const, text };
}

export function mockModel() {
  const parts = (prompt: Prompt) => {
    const p = plan(prompt);
    return p.kind === "tool"
      ? { content: [{ type: "tool-call" as const, toolCallId: "call_1", toolName: "match_listings", input: p.input }], finish: "tool-calls" as const }
      : { content: [{ type: "text" as const, text: p.text }], finish: "stop" as const };
  };
  return new MockLanguageModelV3({
    doGenerate: async ({ prompt }) => {
      const r = parts(prompt as Prompt);
      return { content: r.content, finishReason: { unified: r.finish, raw: r.finish }, usage, warnings: [] };
    },
    doStream: async ({ prompt }) => {
      const r = parts(prompt as Prompt);
      const chunks: unknown[] = [{ type: "stream-start", warnings: [] }];
      for (const c of r.content) {
        if (c.type === "text") chunks.push({ type: "text-start", id: "t1" }, { type: "text-delta", id: "t1", delta: c.text }, { type: "text-end", id: "t1" });
        else chunks.push(c);
      }
      chunks.push({ type: "finish", finishReason: { unified: r.finish, raw: r.finish }, usage });
      return { stream: new ReadableStream({ start(ctrl) { chunks.forEach((c) => ctrl.enqueue(c)); ctrl.close(); } }) } as never;
    },
  });
}
