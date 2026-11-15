"use client";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { btnCls, inputCls } from "./styles";
import { Bar, BedsSelect, Card, Disclaimer, ErrorNote, Field, MockFlag, ZipSelect } from "./ui";
import { errorMessage, isMock } from "@/lib/api";
import { usd } from "@/lib/format";
import { postOwnerReach } from "@/lib/night-api";
import type { OwnerReachResponse } from "@/lib/night-types";

const FACTS = ["pets", "parking", "laundry", "air_conditioning", "utilities_included"];

export default function OwnerReach() {
  const [zip, setZip] = useState("92104");
  const [beds, setBeds] = useState("1");
  const [target, setTarget] = useState("");
  const [text, setText] = useState("");
  const [res, setRes] = useState<OwnerReachResponse | null>(null);
  const [target0, setTarget0] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const r = await postOwnerReach({ zip, beds: Number(beds), target_rent: Number(target), text: text.trim() || null });
      setRes(r);
      setTarget0(Number(target));
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="ZIP"><ZipSelect value={zip} onChange={setZip} /></Field>
          <Field label="Bedrooms"><BedsSelect value={beds} onChange={setBeds} /></Field>
          <Field label="Rent you plan to ask ($)"><input className={inputCls} type="number" inputMode="decimal" min="1" step="any" value={target} onChange={(e) => setTarget(e.target.value)} required /></Field>
        </div>
        <Field label="Your listing text (optional)" hint={`We read which of these it states: ${FACTS.map((f) => f.replace("_", " ")).join(", ")}. Nothing is posted anywhere.`}>
          <textarea className={`${inputCls} min-h-28`} value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
        </Field>
        <button className={`${btnCls} w-full sm:w-auto`} disabled={busy}>{busy ? "Estimating..." : "Estimate reach"}</button>
        {err && <ErrorNote>{err}</ErrorNote>}
      </form>

      {res && (
        <div className="space-y-4" aria-live="polite">
          <MockFlag on={isMock(res)} />
          <Card className="space-y-3">
            <h2 className="text-lg font-bold">Estimated reach at {usd(target0 || res.curve[0]?.rent_usd)}</h2>
            <Bar value={res.current_reach_pct} label="Share of renter profiles that would shortlist it" />
            <div className="h-56 w-full" role="img" aria-label="Reach by asking rent: the higher the rent, the fewer renter profiles would shortlist it">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={res.curve} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="var(--grid)" strokeOpacity={0.45} vertical={false} />
                  <XAxis dataKey="rent_usd" tickFormatter={(v: number) => `$${v}`} fontSize={11} minTickGap={24} />
                  <YAxis width={40} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} fontSize={11} />
                  <Tooltip formatter={(v: unknown) => [`${v}%`, "Reach"]} labelFormatter={(l) => `Rent ${usd(Number(l))}`} />
                  <Line dataKey="reach_pct" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                  <ReferenceDot x={res.curve.reduce((a, p) => (Math.abs(p.reach_pct - res.current_reach_pct) < Math.abs(a.reach_pct - res.current_reach_pct) ? p : a)).rent_usd} y={res.current_reach_pct} r={6} fill="var(--accent-strong)" stroke="var(--surface)" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className="space-y-2">
            <h2 className="text-lg font-bold">Changes that would help most</h2>
            {res.best_changes.length === 0 ? <p className="text-sm text-muted">No single change adds much reach.</p> : (
              <ul className="divide-y divide-line">
                {res.best_changes.map((c) => (
                  <li key={c.label} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <span className="min-w-0 font-medium">{c.label}</span>
                    <span className="tabular-nums text-muted">{Math.round(c.reach_before_pct)}% to {Math.round(c.reach_after_pct)}% <strong className="text-good">(+{c.gain_pts.toFixed(0)} pts)</strong></span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="space-y-2">
            <h2 className="text-lg font-bold">Renter profiles used</h2>
            <ul className="space-y-1 text-sm">
              {res.profiles.map((p) => (
                <li key={p.id} className="flex justify-between gap-3"><span className="min-w-0">{p.label}</span><span className="shrink-0 tabular-nums text-muted">{Math.round(p.weight * 100)}% of demand</span></li>
              ))}
            </ul>
            <p className="text-xs text-muted">{res.method_note} Based on {res.n_comparables} comparable listings.</p>
          </Card>
          <Disclaimer text={res.disclaimer} />
        </div>
      )}
    </div>
  );
}
