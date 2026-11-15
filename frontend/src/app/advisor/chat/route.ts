// POST /advisor/chat (never under /api: Caddy sends /api/* to FastAPI).
//  - useChat body ({ messages }): streams the AI SDK UI message stream.
//  - { text }: answers once as JSON { answer, steps, ungrounded } for the typed client and tests.
// The key stays on the server. At most MAX_STEPS tool steps per message, enforced here, not by the client.
import { handleChatStream } from "@mastra/ai-sdk";
import { createUIMessageStreamResponse } from "ai";
import { MAX_STEPS, makeMastra } from "@/advisor";
import { ungroundedFigures } from "@/advisor/figures";


const MAX_TEXT = 1500;
const cache = new Map<string, { answer: string; steps: number; ungrounded: string[] }>();
let mastra: ReturnType<typeof makeMastra> | null = null;

async function getMastra() {
  if (!mastra) {
    let model;
    if (process.env.ADVISOR_MOCK === "1" && process.env.NODE_ENV !== "production") {
      model = (await import("@/advisor/mock")).mockModel();
    }
    mastra = makeMastra(model as never);
  }
  return mastra;
}

export async function POST(req: Request) {
  let body: { text?: string; messages?: unknown[] };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Send JSON" }, { status: 400 });
  }
  const m = await getMastra();

  if (typeof body.text === "string") {
    const text = body.text.trim().slice(0, MAX_TEXT);
    if (text.length < 3) return Response.json({ error: "Ask a longer question" }, { status: 400 });
    const hit = cache.get(text);
    if (hit) return Response.json({ ...hit, cached: true });
    const res = await m.getAgent("advisor").generate(text, { maxSteps: MAX_STEPS });
    const results = (res.toolResults ?? []).map((t: { payload?: { result?: unknown }; result?: unknown }) => t.payload?.result ?? t.result);
    const out = { answer: res.text, steps: res.steps?.length ?? 0, ungrounded: ungroundedFigures(res.text, results) };
    if (!out.ungrounded.length) {
      if (cache.size > 200) cache.clear();
      cache.set(text, out);
    }
    return Response.json({ ...out, cached: false });
  }

  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return Response.json({ error: "Send messages or text" }, { status: 400 });
  }
  const stream = await handleChatStream({
    mastra: m,
    agentId: "advisor",
    version: "v7",
    params: { messages: body.messages as never, maxSteps: MAX_STEPS },
    defaultOptions: { maxSteps: MAX_STEPS },
  });
  return createUIMessageStreamResponse({ stream });
}
