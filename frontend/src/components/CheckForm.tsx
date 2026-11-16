"use client";
import { useState } from "react";
import { postCheck, searchUnits, errorMessage } from "@/lib/api";
import type { CheckResponse, PropertyType, UnitMatch } from "@/lib/contract";
import { btnCls, btnGhostCls, inputCls } from "./styles";
import { ErrorNote, Field, TriState, triToBool } from "./ui";
import { VerdictCard } from "./cards";
import { usePrefill } from "@/lib/useprefill";

export default function CheckForm({ prefill }: { prefill?: { address: string; zip: string; year: string } }) {
  // Query parameters (lib/prefill.ts) fill the fields; nothing is submitted until the person presses the button.
  const q = usePrefill();
  const [address, setAddress] = useState(q.text("address", 200) || prefill?.address || "");
  const [zip, setZip] = useState(q.zip() || prefill?.zip || "");
  const [lowest, setLowest] = useState(q.num("lowest"));
  const [next, setNext] = useState(q.num("new"));
  const [date, setDate] = useState(q.date("effective"));
  const [year, setYear] = useState(q.year() || q.year("year_built") || prefill?.year || "");
  const [ptype, setPtype] = useState<PropertyType>((q.homeType() || "unknown") as PropertyType);
  const [notice, setNotice] = useState(q.yesNo("notice"));
  const [corp, setCorp] = useState(q.yesNo("corp"));
  const [other, setOther] = useState(false);
  const [incs, setIncs] = useState(q.int("increases") || "0");
  const [matches, setMatches] = useState<UnitMatch[] | null>(null);
  const [result, setResult] = useState<CheckResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function lookup() {
    if (address.trim().length < 4) return;
    setMatches((await searchUnits(address.trim())).results);
  }
  function pick(m: UnitMatch) {
    setAddress(m.address_norm + (m.unit_label ? ` ${m.unit_label}` : ""));
    setZip(m.zip);
    if (m.year_built) setYear(String(m.year_built));
    if (m.property_type) setPtype(m.property_type as PropertyType);
    setMatches(null);
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      setResult(
        await postCheck({
          address, zip: zip || null, lowest_rent_12mo: Number(lowest), new_rent: Number(next), effective_date: date,
          year_built: year ? Number(year) : null, property_type: ptype, got_exemption_notice: triToBool(notice),
          owner_is_corporate: triToBool(corp), other_exemption: other, increases_last_12mo: Number(incs) || 0,
        })
      );
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Your address" hint="Look it up to fill in the building's year and type when we have them.">
          <div className="flex gap-2">
            <input className={inputCls} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="4200 Fairmount Ave" required autoComplete="street-address" />
            <button type="button" onClick={lookup} className={btnGhostCls}>Look up</button>
          </div>
        </Field>
        {matches && (
          <ul className="space-y-1 rounded-lg border border-slate-200 bg-surface p-2 text-sm">
            {matches.length === 0 && <li className="px-2 py-1 text-slate-600">No match. Fill in the building details below.</li>}
            {matches.map((m) => (
              <li key={m.property_id}>
                <button type="button" onClick={() => pick(m)} className="w-full rounded px-2 py-2 text-left hover:bg-slate-100">
                  {m.address_norm} {m.unit_label} ({m.zip}){m.year_built ? `, built ${m.year_built}` : ""}
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="ZIP code" hint="Optional."><input className={inputCls} inputMode="numeric" pattern="\d{5}" maxLength={5} value={zip} onChange={(e) => setZip(e.target.value)} placeholder="92104" /></Field>
          <Field label="Lowest rent, past 12 months ($)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={lowest} onChange={(e) => setLowest(e.target.value)} required /></Field>
          <Field label="New rent ($)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={next} onChange={(e) => setNext(e.target.value)} required /></Field>
          <Field label="Takes effect on"><input className={inputCls} type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
          <Field label="Year built"><input className={inputCls} type="number" inputMode="numeric" min="1800" max="2100" value={year} onChange={(e) => setYear(e.target.value)} placeholder="If you know" /></Field>
          <Field label="Home type">
            <select className={inputCls} value={ptype} onChange={(e) => setPtype(e.target.value as PropertyType)}>
              <option value="unknown">Not sure</option>
              <option value="apartment">Apartment</option>
              <option value="condo">Condo</option>
              <option value="townhouse">Townhouse</option>
              <option value="single_family">Single-family home</option>
            </select>
          </Field>
          <Field label="Increases in last 12 months"><input className={inputCls} type="number" inputMode="numeric" min="0" value={incs} onChange={(e) => setIncs(e.target.value)} /></Field>
          <Field label="Did you get an exemption notice?"><TriState value={notice} onChange={setNotice} /></Field>
          <Field label="Is the owner a corporation or REIT?"><TriState value={corp} onChange={setCorp} /></Field>
        </div>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="h-5 w-5" checked={other} onChange={(e) => setOther(e.target.checked)} />
          Owner lives on site in a duplex, it&apos;s a dorm, or the unit is income-restricted
        </label>
        <button className={`${btnCls} w-full`} disabled={busy}>{busy ? "Checking..." : "Check my increase"}</button>
        {err && <ErrorNote>{err}</ErrorNote>}
      </form>
      {result && <VerdictCard r={result} letterHref={`/renter/letter/${result.check_id}?lang=en`} />}
    </div>
  );
}
