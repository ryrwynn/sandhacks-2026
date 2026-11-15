"use client";
import { useState } from "react";
import { evaluateListing } from "@/lib/api";
import type { ListingEvalResponse, PropertyType } from "@/lib/contract";
import { btnCls, inputCls } from "./styles";
import { BedsSelect, ErrorNote, Field, ZipSelect } from "./ui";
import { ListingCheckCard } from "./cards";

export default function ListingForm() {
  const [zip, setZip] = useState("92104");
  const [beds, setBeds] = useState("1");
  const [rent, setRent] = useState("");
  const [baths, setBaths] = useState("");
  const [sqft, setSqft] = useState("");
  const [year, setYear] = useState("");
  const [ptype, setPtype] = useState<PropertyType>("unknown");
  const [text, setText] = useState("");
  const [res, setRes] = useState<ListingEvalResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      setRes(
        await evaluateListing({
          zip, beds: Number(beds), asking_rent: Number(rent), baths: baths ? Number(baths) : null, sqft: sqft ? Number(sqft) : null,
          year_built: year ? Number(year) : null, property_type: ptype, text: text.trim() || null,
        })
      );
    } catch {
      setErr("Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="ZIP code"><ZipSelect value={zip} onChange={setZip} /></Field>
          <Field label="Bedrooms"><BedsSelect value={beds} onChange={setBeds} /></Field>
          <Field label="Asking rent ($/month)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={rent} onChange={(e) => setRent(e.target.value)} required /></Field>
          <Field label="Bathrooms"><input className={inputCls} type="number" inputMode="decimal" min="0" step="0.5" value={baths} onChange={(e) => setBaths(e.target.value)} /></Field>
          <Field label="Square feet"><input className={inputCls} type="number" inputMode="numeric" min="0" value={sqft} onChange={(e) => setSqft(e.target.value)} /></Field>
          <Field label="Year built"><input className={inputCls} type="number" inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} /></Field>
        </div>
        <Field label="Home type">
          <select className={inputCls} value={ptype} onChange={(e) => setPtype(e.target.value as PropertyType)}>
            <option value="unknown">Not sure</option>
            <option value="apartment">Apartment</option>
            <option value="condo">Condo</option>
            <option value="townhouse">Townhouse</option>
            <option value="single_family">Single-family home</option>
          </select>
        </Field>
        <Field label="Paste the listing text (optional)" hint="We read missing facts like bathrooms or square feet from it.">
          <textarea className={inputCls} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
        <button className={`${btnCls} w-full`} disabled={busy}>{busy ? "Checking..." : "Check this price"}</button>
        {err && <ErrorNote>{err}</ErrorNote>}
      </form>
      {res && <ListingCheckCard r={res} />}
    </div>
  );
}
