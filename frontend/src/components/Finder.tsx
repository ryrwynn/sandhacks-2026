"use client";
import { useEffect, useState } from "react";
import { rankNeighborhoods, errorMessage } from "@/lib/api";
import type { Persona, RankResponse, ZipSummary } from "@/lib/contract";
import { btnCls, inputCls } from "./styles";
import ZipMap from "./ZipMap";
import { RankedZipCard } from "./cards";
import { BedsSelect, Disclaimer, ErrorNote, Field } from "./ui";

/** Starter finder (renter) and Wealth builder finder (buyer): budget and bedrooms in, ranked ZIPs out. */
export default function Finder({
  persona, token, zips, showMap = false, onPickZip,
}: { persona: Persona; token?: string | null; zips?: ZipSummary[]; showMap?: boolean; onPickZip?: (zip: string) => void }) {
  const wealth = persona === "wealth";
  const [budget, setBudget] = useState(wealth ? "900000" : "3000");
  const [beds, setBeds] = useState("");
  const [res, setRes] = useState<RankResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function run(b = budget, bd = beds) {
    setErr("");
    setBusy(true);
    try {
      setRes(await rankNeighborhoods({ persona, budget_usd: Number(b), beds: bd === "" ? null : Number(bd) }));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    run();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const priceLabel = wealth ? "Typical home value" : "Typical rent";
  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); run(); }} className="grid grid-cols-2 gap-3">
        <Field label={wealth ? "Home price budget ($)" : "Monthly rent budget ($)"}>
          <input className={inputCls} type="number" inputMode="numeric" min="1" value={budget} onChange={(e) => setBudget(e.target.value)} required />
        </Field>
        <Field label="Bedrooms"><BedsSelect any value={beds} onChange={setBeds} /></Field>
        <button className={`${btnCls} col-span-2`} disabled={busy}>{busy ? "Ranking..." : wealth ? "Find wealth-building ZIPs" : "Find a place"}</button>
      </form>
      {err && <ErrorNote>{err}</ErrorNote>}
      {res && (
        <>
          {showMap && token !== undefined && zips && <ZipMap token={token ?? null} zips={zips} highlight={res.ranked.map((z) => z.zip)} />}
          <p className="text-sm text-slate-600">
            {wealth
              ? "Ranked by expected appreciation, rental yield and fit to your budget."
              : "Ranked for low rent and short trips to groceries and transit; other amenities count lightly."}
          </p>
          <div className="space-y-3">
            {res.ranked.length === 0 && <p className="text-sm text-slate-700">No ZIPs fit this budget. See the stretch list below.</p>}
            {res.ranked.map((z) => <RankedZipCard key={z.zip} z={z} priceLabel={priceLabel} onPick={onPickZip} />)}
          </div>
          {res.stretch.length > 0 && (
            <div className="space-y-3">
              <h2 className="font-semibold">Stretch: above your budget</h2>
              {res.stretch.map((z) => <RankedZipCard key={z.zip} z={z} stretch priceLabel={priceLabel} onPick={onPickZip} />)}
            </div>
          )}
          <Disclaimer kind="estimate" text={res.disclaimer} />
        </>
      )}
    </div>
  );
}
