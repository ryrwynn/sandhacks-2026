"use client";
import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import ApartmentCard from "./ApartmentCard";
import { btnCls, inputCls } from "./styles";
import { Card, Disclaimer, ErrorNote, MockFlag } from "./ui";
import { askAdvisor, type AdvisorMessage } from "@/lib/advisor-client";
import { errorMessage, isMock } from "@/lib/api";
import { postMatch } from "@/lib/night-api";
import type { MatchResponse } from "@/lib/night-types";
import { useSaved } from "@/lib/saved";
import { usd } from "@/lib/format";

const STARTERS = ["Is a 12% rent increase legal in San Diego?", "Which ZIPs are getting cheaper?", "What can I do if my landlord raised rent during a wildfire emergency?"];

/** Chat with the housing advisor. All network access is in lib/advisor-client.ts. */
export function AdvisorChat() {
  const [msgs, setMsgs] = useState<AdvisorMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [msgs]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    const next: AdvisorMessage[] = [...msgs, { role: "user", content: t }];
    setMsgs([...next, { role: "assistant", content: "" }]);
    setInput("");
    setErr("");
    setBusy(true);
    abort.current = new AbortController();
    try {
      let acc = "";
      let links: AdvisorMessage["links"];
      for await (const chunk of askAdvisor(next, abort.current.signal)) {
        if (typeof chunk === "string") acc += chunk; else links = chunk;
        setMsgs([...next, { role: "assistant", content: acc, links }]);
      }
      if (!acc) setMsgs(next);
    } catch (e) {
      setErr(errorMessage(e));
      setMsgs(next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold">Ask the housing advisor</h2>
      <div className="max-h-[28rem] min-h-32 space-y-2 overflow-y-auto" role="log" aria-live="polite" aria-label="Conversation">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-muted">Ask about rents, forecasts, the rent cap or price gouging. Try one of these:</p>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              {STARTERS.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} className="min-h-11 rounded-lg bg-bg px-3 py-2 text-left text-sm hover:bg-line">{s}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`max-w-[92%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "ml-auto bg-primary text-on-primary" : "bg-bg"}`}>
            <span className="sr-only">{m.role === "user" ? "You: " : "Advisor: "}</span>
            {m.content || (busy ? "Thinking..." : "")}
            {m.links?.map((l) => (
              <a key={l.url} href={l.url} className={`${btnCls} mt-2 block w-full text-center sm:w-auto`}>{l.button}</a>
            ))}
          </div>
        ))}
        <div ref={end} />
      </div>
      {err && <ErrorNote>{err}</ErrorNote>}
      <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex gap-2">
        <input className={inputCls} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question" aria-label="Your question" maxLength={1000} />
        <button className={`${btnCls} shrink-0 gap-1.5`} disabled={busy || !input.trim()}><Send size={18} aria-hidden="true" /> Send</button>
      </form>
      <p className="text-xs text-muted">The advisor explains public data and rules. It is not legal or financial advice, and it never contacts anyone for you.</p>
    </Card>
  );
}

/** "Find by needs": plain-language needs matched against listings (POST /match). */
export function MatchPanel() {
  const [text, setText] = useState("");
  const [res, setRes] = useState<MatchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const { has, toggle } = useSaved();

  async function go(e: React.FormEvent) {
    e.preventDefault();
    if (text.trim().length < 3) return;
    setErr("");
    setBusy(true);
    try { setRes(await postMatch({ text: text.trim(), limit: 10 })); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  const n = res?.needs;
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold">Find by needs</h2>
      <form onSubmit={go} className="space-y-2">
        <textarea className={`${inputCls} min-h-24`} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} aria-label="Describe what you need" placeholder="Quiet 1 bedroom under $2,400 near UCSD, cat ok, parking" />
        <button className={`${btnCls} w-full sm:w-auto`} disabled={busy}>{busy ? "Matching..." : "Find matches"}</button>
      </form>
      {err && <ErrorNote>{err}</ErrorNote>}
      {res && n && (
        <div className="space-y-3" aria-live="polite">
          <MockFlag on={isMock(res)} />
          <p className="text-sm text-muted">
            We read: {n.budget_max_usd != null && <>up to {usd(n.budget_max_usd)}; </>}
            {n.beds_min != null && <>{n.beds_min}+ bedrooms; </>}
            {n.must_haves.length > 0 && <>must have {n.must_haves.join(", ")}; </>}
            {n.nice_to_haves.length > 0 && <>nice to have {n.nice_to_haves.join(", ")}; </>}
            {n.commute_anchors.length > 0 && <>near {n.commute_anchors.join(", ")}; </>}
            ({n.parsed_by === "gemini" ? "read by AI" : "read by rules"}, {res.method === "embeddings" ? "meaning match" : "keyword match"}, {res.n_after_filters} of {res.n_candidates} listings fit)
          </p>
          {res.results.length === 0 ? <p className="text-sm">No listings fit. Try a higher budget or fewer must-haves.</p> : (
            <ol className="space-y-4">
              {res.results.map((m) => (
                <li key={m.listing.id} className="space-y-2">
                  <ApartmentCard listing={m.listing} showSave saved={has(m.listing.id)} onToggle={() => toggle(m.listing)} />
                  <div className="space-y-1 px-1 text-sm">
                    <p className="font-semibold">Match score {Math.round(m.score)} of 100</p>
                    <ul className="list-disc pl-5 text-muted">{m.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                    {m.unconfirmed.length > 0 && <p className="text-xs text-muted">Not stated in the listing: {m.unconfirmed.join(", ")}.</p>}
                  </div>
                </li>
              ))}
            </ol>
          )}
          <Disclaimer kind="estimate" text={res.disclaimer} />
        </div>
      )}
    </Card>
  );
}
