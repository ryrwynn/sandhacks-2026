"use client";
import { useState } from "react";
import { btnCls, inputCls } from "./styles";
import { BedsSelect, Card, Disclaimer, ErrorNote, Field, MockFlag } from "./ui";
import { errorMessage, isMock } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import { postGouging } from "@/lib/night-api";
import type { GougingResponse, GougingVerdict } from "@/lib/night-types";
import { fmtDate } from "@/lib/tracker";

export const NOT_LEGAL_ADVICE = "This is not legal advice. Penal Code 396 applies only during a declared emergency.";
const DEFAULT_LINKS = [
  { label: "Legal Aid Society of San Diego", url: "https://www.lassd.org/" },
  { label: "California Attorney General: price gouging", url: "https://oag.ca.gov/consumers/pricegougingduringdisasters" },
];

const VERDICT: Record<GougingVerdict, { title: string; cls: string }> = {
  likely_violation: { title: "This price is likely over the legal limit", cls: "bg-red-50 text-red-800" },
  within_limit: { title: "This price is within the legal limit", cls: "bg-emerald-50 text-emerald-800" },
  not_covered: { title: "Gouging limits do not appear to apply", cls: "bg-slate-100 text-slate-700" },
  unclear: { title: "We cannot tell from what was entered", cls: "bg-amber-50 text-amber-900" },
};

export function GougingResult({ r }: { r: GougingResponse }) {
  const v = VERDICT[r.verdict];
  const links = r.links?.length ? r.links : DEFAULT_LINKS;
  return (
    <div className="space-y-3" aria-live="polite">
      <div className={`rounded-xl p-4 ${v.cls}`}>
        <h2 className="text-lg font-bold">{v.title}</h2>
        {r.limit_usd != null && (
          <p className="mt-1">
            Highest price allowed: <strong className="tabular-nums">{usd(r.limit_usd)}</strong>
            {r.increase_pct != null && <> (this is {pct(r.increase_pct, 1, true)} from the pre-emergency rent)</>}
          </p>
        )}
        {r.basis !== "none" && (
          <p className="mt-1 text-sm">
            Basis: {r.basis === "pre_emergency_plus_10" ? "10% above the price before the emergency" : "160% of HUD fair market rent"}
            {r.fmr_usd != null && <>, HUD figure {usd(r.fmr_usd)}</>}{r.fmr_source && <> ({r.fmr_source})</>}.
          </p>
        )}
      </div>
      {r.emergency && (
        <Card className="space-y-1 text-sm">
          <h3 className="font-semibold">{r.emergency.title}</h3>
          <p className="text-muted">
            Declared {fmtDate(r.emergency.declared_on)}
            {r.emergency.protections_until && <>, protections until {fmtDate(r.emergency.protections_until)}</>}
            {r.emergency.counties.length > 0 && <>. Counties: {r.emergency.counties.join(", ")}</>}.
          </p>
          <a href={r.emergency.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center font-medium text-accent-strong underline underline-offset-2">Source</a>
        </Card>
      )}
      <ul className="list-disc space-y-1 pl-5 text-sm">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
      <Card className="space-y-1">
        <h3 className="font-semibold">Where to get help</h3>
        <ul className="text-sm">
          {links.map((l) => (
            <li key={l.url}><a href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center font-medium text-accent-strong underline underline-offset-2">{l.label}</a></li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export default function GougingCheck() {
  const [zip, setZip] = useState("");
  const [rent, setRent] = useState("");
  const [date, setDate] = useState("");
  const [before, setBefore] = useState("");
  const [beds, setBeds] = useState("");
  const [res, setRes] = useState<GougingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      setRes(await postGouging({
        zip: zip || null, new_rent: Number(rent), offer_date: date,
        pre_emergency_rent: before ? Number(before) : null, beds: beds === "" ? null : Number(beds),
      }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium" role="note">{NOT_LEGAL_ADVICE} For help, contact the Legal Aid Society of San Diego or the California Attorney General.</p>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="ZIP code" hint="Used to find the county and the HUD fair market rent."><input className={inputCls} inputMode="numeric" pattern="\d{5}" maxLength={5} value={zip} onChange={(e) => setZip(e.target.value)} placeholder="92104" /></Field>
          <Field label="Bedrooms"><BedsSelect value={beds} onChange={setBeds} any /></Field>
          <Field label="New rent charged or offered ($)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={rent} onChange={(e) => setRent(e.target.value)} required /></Field>
          <Field label="Date it was charged or offered"><input className={inputCls} type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
          <Field label="Rent before the emergency ($)" hint="Leave blank if the unit was not rented or offered before."><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={before} onChange={(e) => setBefore(e.target.value)} /></Field>
        </div>
        <button className={`${btnCls} w-full sm:w-auto`} disabled={busy}>{busy ? "Checking..." : "Check for price gouging"}</button>
        {err && <ErrorNote>{err}</ErrorNote>}
      </form>
      {res && (
        <>
          <MockFlag on={isMock(res)} />
          <GougingResult r={res} />
          <Disclaimer text={res.disclaimer} />
        </>
      )}
    </div>
  );
}
