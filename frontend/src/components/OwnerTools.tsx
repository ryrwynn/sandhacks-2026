"use client";
import { useState } from "react";
import { getListingAnalysis, getPricePosition, errorMessage } from "@/lib/api";
import type { ListingAnalysisResponse, PricePositionResponse, PropertyType } from "@/lib/contract";
import { pct, usd } from "@/lib/format";
import { btnCls, inputCls } from "./styles";
import { Bar, BedsSelect, Card, Disclaimer, ErrorNote, Field, TriState, triToBool, ZipSelect } from "./ui";
import { ListingAnalysisCard } from "./cards";

const LABELS = { low: "Low (10th percentile)", expected: "Expected", high: "High (90th percentile)", target: "Your target" } as const;

export default function OwnerTools() {
  const [zip, setZip] = useState("92104");
  const [beds, setBeds] = useState("2");
  const [target, setTarget] = useState("");
  const [sqft, setSqft] = useState("");
  const [year, setYear] = useState("");
  const [ptype, setPtype] = useState<PropertyType>("unknown");
  const [occupied, setOccupied] = useState(false);
  const [lowest, setLowest] = useState("");
  const [date, setDate] = useState("");
  const [notice, setNotice] = useState("");
  const [corp, setCorp] = useState("");
  const [pos, setPos] = useState<PricePositionResponse | null>(null);
  const [text, setText] = useState("");
  const [ana, setAna] = useState<ListingAnalysisResponse | null>(null);
  const [busy, setBusy] = useState<"" | "pos" | "ana">("");
  const [err, setErr] = useState("");

  async function price(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy("pos");
    try {
      setPos(
        await getPricePosition({
          zip, beds: Number(beds), target_rent: Number(target), sqft: sqft ? Number(sqft) : null, year_built: year ? Number(year) : null,
          property_type: ptype, occupied, lowest_rent_12mo: occupied && lowest ? Number(lowest) : null,
          effective_date: occupied && date ? date : null, got_exemption_notice: triToBool(notice), owner_is_corporate: triToBool(corp),
        })
      );
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy("");
    }
  }
  async function analyze() {
    setErr("");
    setBusy("ana");
    try {
      setAna(await getListingAnalysis({ zip, beds: Number(beds), text: text.trim(), target_rent: target ? Number(target) : null }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={price} className="space-y-3">
        <h2 className="text-lg font-bold">Price position</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="ZIP code"><ZipSelect value={zip} onChange={setZip} /></Field>
          <Field label="Bedrooms"><BedsSelect value={beds} onChange={setBeds} /></Field>
          <Field label="Target rent ($/month)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={target} onChange={(e) => setTarget(e.target.value)} required /></Field>
          <Field label="Square feet"><input className={inputCls} type="number" inputMode="numeric" min="0" value={sqft} onChange={(e) => setSqft(e.target.value)} /></Field>
          <Field label="Year built"><input className={inputCls} type="number" inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} /></Field>
          <Field label="Home type">
            <select className={inputCls} value={ptype} onChange={(e) => setPtype(e.target.value as PropertyType)}>
              <option value="unknown">Not sure</option>
              <option value="apartment">Apartment</option>
              <option value="condo">Condo</option>
              <option value="townhouse">Townhouse</option>
              <option value="single_family">Single-family home</option>
            </select>
          </Field>
        </div>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="h-5 w-5" checked={occupied} onChange={(e) => setOccupied(e.target.checked)} />
          A current tenant stays (show the legal maximum)
        </label>
        {occupied && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Tenant's lowest rent, 12 months ($)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={lowest} onChange={(e) => setLowest(e.target.value)} required /></Field>
            <Field label="Increase takes effect"><input className={inputCls} type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
            <Field label="Exemption notice given?"><TriState value={notice} onChange={setNotice} /></Field>
            <Field label="Owner is a corporation or REIT?"><TriState value={corp} onChange={setCorp} /></Field>
          </div>
        )}
        <button className={`${btnCls} w-full`} disabled={busy !== ""}>{busy === "pos" ? "Working..." : "See price position"}</button>
      </form>
      {err && <ErrorNote>{err}</ErrorNote>}

      {pos && (
        <div className="space-y-3">
          <Card className="space-y-3">
            <p className="text-sm text-slate-700">
              Expected rent {usd(pos.estimate.expected)}, range {usd(pos.estimate.low)} to {usd(pos.estimate.high)}, from {pos.n_comparables} comparable listings.
              {pos.estimate.method === "zip_bed_median" && " Based on ZIP and bedroom medians, since the model doesn't have enough data yet."}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr><th className="py-1 pr-2 font-medium">Price point</th><th className="py-1 pr-2 text-right font-medium">Rent</th><th className="py-1 pr-2 text-right font-medium">Percentile</th><th className="py-1 font-medium">Reach</th></tr>
                </thead>
                <tbody>
                  {pos.points.map((p) => (
                    <tr key={p.label} className={`border-t border-slate-100 ${p.label === "target" ? "font-semibold" : ""}`}>
                      <td className="py-2 pr-2">{LABELS[p.label]}</td>
                      <td className="py-2 pr-2 text-right tabular-nums">{usd(p.rent_usd)}</td>
                      <td className="py-2 pr-2 text-right tabular-nums">{p.percentile != null ? Math.round(p.percentile) : "n/a"}</td>
                      <td className="min-w-24 py-2">{p.reach_score != null ? <Bar value={p.reach_score} label="Reach" /> : "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-600">Reach is a prediction of how many renters are likely to consider this price, not measured clicks.</p>
            {pos.days_on_market ? (
              <p className="text-sm">
                Comparable listings below the expected rent stayed up {pos.days_on_market.below_expected_median_days ?? "n/a"} days (median) and above it {pos.days_on_market.above_expected_median_days ?? "n/a"} days, across {pos.days_on_market.n_listings} listings.
              </p>
            ) : (
              <p className="text-xs text-slate-600">Days on market isn&apos;t shown: the data doesn&apos;t have enough listing and removal dates yet.</p>
            )}
            <Disclaimer kind="estimate" text={pos.disclaimer} />
          </Card>
          {pos.legal && (
            <Card className="space-y-2 border-amber-300 bg-amber-50">
              <h3 className="font-bold">Legal guardrail for an occupied unit</h3>
              <p className="text-sm">
                {pos.legal.verdict === "not_covered" ? "The state rent cap does not appear to apply to this unit." : pos.legal.verdict === "unclear" ? "We need more information to say whether the cap applies." : "The state rent cap (AB 1482) applies."}
                {pos.legal.max_legal_rent != null && <> The most you can charge the current tenant is <b>{usd(pos.legal.max_legal_rent, 2)}</b>{pos.legal.cap_pct != null && <> ({pct(pos.legal.cap_pct)} cap)</>}.</>}
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm">{pos.legal.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <Disclaimer kind="legal" />
            </Card>
          )}
        </div>
      )}

      <div className="space-y-3">
        <h2 className="text-lg font-bold">Listing analysis</h2>
        <Field label="Paste your listing text" hint="Uses the ZIP and bedrooms above. We score completeness against comparable listings and never rewrite your text.">
          <textarea className={inputCls} rows={5} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
        <button className={`${btnCls} w-full`} onClick={analyze} disabled={busy !== "" || text.trim().length < 10}>{busy === "ana" ? "Analyzing..." : "Analyze my listing"}</button>
        {ana && <ListingAnalysisCard r={ana} />}
      </div>
    </div>
  );
}
