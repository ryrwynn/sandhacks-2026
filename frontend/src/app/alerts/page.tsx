"use client";
import Link from "next/link";
import { useState } from "react";
import { Delta } from "@/components/ApartmentCard";
import { cardCls, inputCls } from "@/components/styles";
import { usd } from "@/lib/format";
import { alertOf, useSaved } from "@/lib/saved";
import { fmtDate } from "@/lib/tracker";

function TargetForm({ id, target, price }: { id: number; target?: number | null; price: number }) {
  const { setTarget } = useSaved();
  const [v, setV] = useState(target != null ? String(target) : "");
  const n = Number(v);
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => { e.preventDefault(); setTarget(id, v.trim() === "" ? null : n > 0 ? n : null); }}
    >
      <label className="block">
        <span className="mb-1 block text-sm font-medium">Alert me at or below ($ / month)</span>
        <input className={`${inputCls} w-44`} type="number" inputMode="numeric" min="1" step="25" value={v} placeholder={String(Math.round(price * 0.95 / 25) * 25)} onChange={(e) => setV(e.target.value)} />
      </label>
      <button className="min-h-11 rounded-lg bg-primary px-4 font-semibold text-white hover:bg-primary-hover">Set target</button>
      {target != null && (
        <button type="button" onClick={() => { setV(""); setTarget(id, null); }} className="min-h-11 rounded-lg px-3 font-medium text-accent-strong underline underline-offset-2">Clear</button>
      )}
    </form>
  );
}

export default function Alerts() {
  const { items, listings, ready, loading, markSeen } = useSaved();
  const rows = items.map((item) => ({ item, l: listings[item.id] })).filter((x) => x.l);
  const hits = rows
    .map((r) => ({ ...r, kind: alertOf(r.item, r.l) }))
    .filter((r) => r.kind)
    .sort((a, b) => +new Date(b.l.last_seen) - +new Date(a.l.last_seen));

  return (
    <main className="space-y-6">
      <section>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Price alerts</h1>
        <p className="text-muted">Set a target rent for any saved apartment. Alerts show here and with a badge in the menu. RentOrKnot never sends email, texts or push notifications, and asks for no contact details.</p>
      </section>

      {!ready || (loading && rows.length === 0) ? (
        <div className="skeleton h-40" aria-label="Loading alerts" />
      ) : items.length === 0 ? (
        <div className={`${cardCls} p-8 text-center`}>
          <p className="text-lg font-semibold">No saved apartments to watch yet.</p>
          <p className="mb-4 text-muted">Save an apartment, then set a target rent here.</p>
          <Link href="/find" className="inline-flex min-h-11 items-center rounded-lg bg-primary px-5 font-semibold text-white hover:bg-primary-hover">Find apartments</Link>
        </div>
      ) : (
        <>
          <section aria-labelledby="hit-h" className="space-y-3">
            <h2 id="hit-h" className="text-xl font-bold">Needs a look <span className="text-base font-normal text-muted">· {hits.length}</span></h2>
            {hits.length === 0 ? (
              <p className={`${cardCls} p-5 text-muted`}>Nothing has hit a target or changed price since you last looked. Check back after the next update.</p>
            ) : (
              <ul className="space-y-3">
                {hits.map(({ item, l, kind }) => (
                  <li key={item.id} className={`${cardCls} flex flex-wrap items-center justify-between gap-3 p-4`}>
                    <div className="min-w-0">
                      <Link href={`/apartments/${l.id}`} className="font-bold underline decoration-line underline-offset-2">{l.address ?? "Address not listed"}</Link>
                      <p className="text-sm text-muted">
                        {kind === "target" ? `Below your target of ${usd(item.target)}` : "Price changed since you last checked"} · last seen {fmtDate(l.last_seen)}
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="text-xl font-bold tabular-nums">{usd(l.current_price_usd)}</div>
                        <Delta now={l.current_price_usd} then={item.seenPrice ?? item.priceAtSave} suffix="since you last checked" />
                      </div>
                      <button type="button" onClick={() => markSeen(item.id)} className="min-h-11 rounded-lg bg-bg px-4 font-medium hover:bg-line">Got it</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="targets-h" className="space-y-3">
            <h2 id="targets-h" className="text-xl font-bold">Your targets</h2>
            <ul className="space-y-3">
              {rows.map(({ item, l }) => (
                <li key={item.id} className={`${cardCls} space-y-3 p-4`}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <Link href={`/apartments/${l.id}`} className="font-bold underline decoration-line underline-offset-2">{l.address ?? "Address not listed"}</Link>
                    <span className="text-muted">Now <strong className="text-ink tabular-nums">{usd(l.current_price_usd)}</strong>{item.target != null && <> · target <strong className="text-ink tabular-nums">{usd(item.target)}</strong></>}</span>
                  </div>
                  <TargetForm key={`${item.id}-${item.target ?? ""}`} id={item.id} target={item.target} price={l.current_price_usd} />
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
