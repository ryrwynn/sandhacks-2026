"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usd } from "@/lib/format";
import { bedsText, changeOf, FAIR_LABEL, fmtDate, fmtMonth, type ListingSummary } from "@/lib/tracker";
import { cardCls } from "./styles";
import Sparkline from "./Sparkline";

/** "↓ $100 (3.3%)" with words for screen readers, colored good for drops and warn for rises. */
export function Delta({ now, then, suffix }: { now: number; then: number; suffix?: string }) {
  const c = changeOf(now, then);
  const word = c.dir === "down" ? "down" : c.dir === "up" ? "up" : "unchanged";
  const tone = c.dir === "down" ? "text-good" : c.dir === "up" ? "text-warn" : "text-muted";
  return (
    <span className={`text-sm font-medium ${tone}`}>
      <span aria-hidden="true">{c.arrow} {c.dir === "flat" ? "No change" : `${usd(Math.abs(c.diff))} (${c.pct.toFixed(1)}%)`}</span>
      <span className="sr-only">{c.dir === "flat" ? "No change" : `${word} ${usd(Math.abs(c.diff))}, ${c.pct.toFixed(1)} percent`}</span>
      {suffix && <span className="block text-xs font-normal text-muted">{suffix}</span>}
    </span>
  );
}

function RemoveMenu({ onRemove, label }: { onRemove: () => void; label: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={box} className="relative z-10">
      <button type="button" aria-label={`More options for ${label}`} aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((o) => !o)}
        className="flex h-11 w-11 items-center justify-center rounded-full text-muted hover:bg-bg">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-48 rounded-xl bg-surface p-1 shadow-[0_6px_24px_rgba(46,49,39,0.2)]">
          <button type="button" onClick={() => { setOpen(false); onRemove(); }} className="flex min-h-11 w-full items-center rounded-lg px-3 text-left text-base text-warn hover:bg-bg">
            Remove from saved
          </button>
        </div>
      )}
    </div>
  );
}

export default function ApartmentCard({ listing: l, saved, onToggle, onRemove, showSave, note, sinceSaved }: {
  listing: ListingSummary;
  saved?: boolean;
  onToggle?: () => void;
  onRemove?: () => void;
  showSave?: boolean;
  note?: string;                  // e.g. "Example: remove anytime"
  sinceSaved?: number;            // price when saved; shows "since you saved it"
}) {
  const isRent = l.listing_type === "rent";
  const title = [l.address ?? "Address not listed", l.unit_label ? `#${l.unit_label}` : null].filter(Boolean).join(" ");
  const facts = [l.neighborhood, bedsText(l.beds), l.sqft ? `${l.sqft.toLocaleString()} sq ft` : null].filter(Boolean).join(" · ");
  const many = l.sparkline.length > 1 && l.n_observations > 1;
  const first = l.sparkline[0], last = l.sparkline[l.sparkline.length - 1];
  return (
    <article className={`${cardCls} relative flex flex-col p-4 transition-shadow focus-within:outline focus-within:outline-2 focus-within:outline-primary hover:shadow-[0_2px_6px_rgba(46,49,39,0.18),0_8px_22px_rgba(46,49,39,0.08)]`}>
      {note && <p className="mb-2 w-fit rounded-full bg-line px-2.5 py-0.5 text-xs font-medium text-ink">{note}</p>}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-bold leading-snug">
            <Link href={`/apartments/${l.id}`} className="outline-none after:absolute after:inset-0 after:content-[''] focus-visible:after:rounded-xl focus-visible:after:outline focus-visible:after:outline-2 focus-visible:after:outline-primary">
              {title}
            </Link>
          </h3>
          {facts && <p className="text-sm text-muted">{facts}</p>}
        </div>
        <div className="relative z-10 -mr-2 -mt-2 flex shrink-0">
          {l.source_url && (
            <a href={l.source_url} target="_blank" rel="noopener noreferrer" aria-label={`Open the listing for ${title} in a new tab`}
              className="flex h-11 w-11 items-center justify-center rounded-full text-muted hover:bg-bg">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
            </a>
          )}
          {onRemove && <RemoveMenu onRemove={onRemove} label={title} />}
        </div>
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <p><strong className="text-2xl font-bold tabular-nums tracking-tight">{usd(l.current_price_usd)}</strong><span className="text-sm text-muted">{isRent ? " / mo" : " asking price"}</span></p>
        <div className="text-right">
          {sinceSaved !== undefined ? (
            <Delta now={l.current_price_usd} then={sinceSaved} suffix="since you saved it" />
          ) : many ? (
            <Delta now={l.current_price_usd} then={l.first_price_usd} suffix="since tracking started" />
          ) : null}
        </div>
      </div>

      <div className="mt-3">
        <Sparkline points={l.sparkline} label={`Asking rent history for ${title}`} />
        <div className="mt-1 flex justify-between text-xs text-muted">
          {many ? (
            <><span>{fmtMonth(first.month)}</span><span>{fmtMonth(last.month)}</span></>
          ) : (
            <span>Tracking since {fmtDate(l.first_observed)}</span>
          )}
        </div>
      </div>

      {isRent && l.fair_rent_label && (
        <p className="mt-3 w-fit rounded-full bg-bg px-2.5 py-1 text-xs font-medium text-ink">{FAIR_LABEL[l.fair_rent_label]}</p>
      )}

      {showSave && onToggle && (
        <button type="button" onClick={onToggle} aria-pressed={!!saved}
          className={`relative z-10 mt-4 min-h-11 w-full rounded-lg px-4 text-base font-semibold ${saved ? "bg-line text-ink" : "bg-primary text-white hover:bg-primary-hover"}`}>
          {saved ? "Saved ✓" : "+ Save apartment"}
        </button>
      )}
    </article>
  );
}

export function CardSkeletons({ n = 4 }: { n?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => <div key={i} className="skeleton h-56" />)}
    </div>
  );
}
