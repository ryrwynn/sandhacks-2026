// Figures rule: every dollar amount and percentage the advisor writes must appear in a tool result.
const NUMBER = /\$\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?%/g;

const norm = (s: string) => s.replace(/[\s$,%]/g, "").replace(/\.0+$/, "");

/** Every amount in the text, normalised ("$2,400" -> "2400"). */
export function figuresIn(text: string): string[] {
  return (text.match(NUMBER) ?? []).map(norm);
}

/** Numbers present in tool results: JSON numbers and numbers inside strings, plus their rounded forms. */
export function groundedFigures(toolResults: unknown[]): Set<string> {
  const out = new Set<string>();
  const add = (n: number) => {
    out.add(norm(String(n)));
    out.add(norm(String(Math.round(n))));
    out.add(norm(n.toFixed(1)));
    out.add(norm(n.toFixed(2)));
  };
  const walk = (v: unknown) => {
    if (typeof v === "number") add(v);
    else if (typeof v === "string") {
      for (const m of v.match(/\d[\d,]*(?:\.\d+)?/g) ?? []) out.add(norm(m));
    } else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  toolResults.forEach(walk);
  return out;
}

/** The figures in `text` that no tool result supports. Empty means grounded. */
export function ungroundedFigures(text: string, toolResults: unknown[]): string[] {
  const ok = groundedFigures(toolResults);
  return figuresIn(text).filter((f) => !ok.has(f));
}
