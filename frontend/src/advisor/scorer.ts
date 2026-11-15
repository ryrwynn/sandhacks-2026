// Scorer for the advisor: 1 when every dollar amount and percentage in the answer comes from a tool result.
import { createScorer } from "@mastra/core/evals";
import { ungroundedFigures } from "./figures";

type Part = { type?: string; text?: string; toolInvocation?: { result?: unknown; state?: string }; output?: unknown; result?: unknown };

/** Pull answer text and tool results out of the run's output messages (shape differs a little by version). */
export function splitRun(output: unknown): { text: string; results: unknown[] } {
  const msgs = Array.isArray(output) ? output : output ? [output] : [];
  let text = "";
  const results: unknown[] = [];
  for (const m of msgs as { role?: string; content?: unknown }[]) {
    const content = m?.content as { parts?: Part[]; content?: string } | string | undefined;
    if (typeof content === "string") { if (m.role === "assistant") text += content + "\n"; continue; }
    if (content?.content && m.role === "assistant") text += content.content + "\n";
    for (const p of content?.parts ?? []) {
      if (p.type === "text" && p.text && m.role === "assistant") text += p.text + "\n";
      if (p.toolInvocation?.result !== undefined) results.push(p.toolInvocation.result);
      else if (p.type?.startsWith("tool-") && (p.output ?? p.result) !== undefined) results.push(p.output ?? p.result);
    }
  }
  return { text, results };
}

export const figuresGrounded = createScorer({
  id: "figures-grounded",
  name: "Figures grounded in tool results",
  description: "Scores 1 when every dollar amount and percentage in the advisor's answer appears in a tool result, else the share that does.",
})
  .generateScore(({ run }) => {
    const { text, results } = splitRun(run.output);
    const total = (text.match(/\$\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?%/g) ?? []).length;
    if (total === 0) return 1;
    const bad = ungroundedFigures(text, results).length;
    return (total - bad) / total;
  });
