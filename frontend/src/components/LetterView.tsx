"use client";
import { useEffect, useState } from "react";
import { postLetter } from "@/lib/api";
import type { Lang, LetterResponse } from "@/lib/contract";
import { btnCls, btnGhostCls, inputCls } from "./styles";
import { Card, Disclaimer, ErrorNote, Field } from "./ui";

const LANGS: { id: Lang; label: string }[] = [
  { id: "en", label: "English" },
  { id: "es", label: "Español" },
  { id: "vi", label: "Tiếng Việt" },
  { id: "tl", label: "Tagalog" },
];

export default function LetterView({ id, initialLang }: { id: string; initialLang: Lang }) {
  const [lang, setLang] = useState<Lang>(initialLang);
  const [res, setRes] = useState<LetterResponse | null>(null);
  const [err, setErr] = useState("");
  // Names are typed here and substituted in the browser only; they are never sent anywhere.
  const [tenant, setTenant] = useState("");
  const [landlord, setLandlord] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    setRes(null);
    setErr("");
    postLetter(id, lang)
      .then((r) => live && setRes(r))
      .catch(() => live && setErr("We couldn't load the letter. Please try again."));
    return () => {
      live = false;
    };
  }, [id, lang]);

  const letter = res?.letter_en
    ? res.letter_en.replaceAll("[Tenant name]", tenant.trim() || "[Tenant name]").replaceAll("[Landlord name]", landlord.trim() || "[Landlord name]")
    : null;

  async function copy() {
    if (!letter) return;
    try {
      await navigator.clipboard.writeText(letter);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable: the print button still works */
    }
  }

  return (
    <div className="space-y-4">
      <div className="print:hidden space-y-4">
        <div role="tablist" aria-label="Language" className="grid grid-cols-4 gap-1 rounded-xl bg-slate-200 p-1">
          {LANGS.map((l) => (
            <button key={l.id} role="tab" aria-selected={lang === l.id} onClick={() => setLang(l.id)}
              className={`min-h-11 rounded-lg px-1 text-sm font-medium ${lang === l.id ? "bg-surface text-indigo-900 shadow" : "text-slate-700"}`}>
              {l.label}
            </button>
          ))}
        </div>
        {err && <ErrorNote>{err}</ErrorNote>}
        {!res && !err && <p className="text-sm text-slate-600" role="status">Loading...</p>}
        {res && (
          <Card>
            <h2 className="mb-2 font-semibold">What this means</h2>
            {res.explanation ? <p className="whitespace-pre-wrap text-sm leading-relaxed">{res.explanation}</p> : <p className="text-sm text-slate-600">An explanation isn&apos;t available right now. The figures in your check result still apply.</p>}
          </Card>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Your name"><input className={inputCls} value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="name" /></Field>
          <Field label="Landlord's name"><input className={inputCls} value={landlord} onChange={(e) => setLandlord(e.target.value)} /></Field>
        </div>
        <p className="text-xs text-slate-600">Names stay in your browser. They are filled into the letter here and never sent to us.</p>
      </div>

      {res && (
        <>
          {letter ? (
            <article aria-label="Letter to your landlord (English)" className="whitespace-pre-wrap rounded-xl border border-slate-300 bg-surface p-5 font-serif text-[15px] leading-relaxed print:border-0 print:p-0">
              {letter}
            </article>
          ) : (
            <p className="text-sm text-slate-600">A draft letter isn&apos;t available right now.</p>
          )}
          <div className="flex gap-2 print:hidden">
            <button className={btnCls} onClick={() => window.print()} disabled={!letter}>Print</button>
            <button className={btnGhostCls} onClick={copy} disabled={!letter}>{copied ? "Copied" : "Copy text"}</button>
          </div>
          <Disclaimer kind="legal" text={res.disclaimer} />
        </>
      )}
    </div>
  );
}
