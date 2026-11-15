"use client";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";
import { getMockSnapshot, markMock, subscribeMock } from "@/lib/mockflag";
import { DISCLAIMER_ESTIMATE, DISCLAIMER_LEGAL } from "@/lib/contract";
import { ZIP_OPTIONS } from "@/lib/format";

import { inputCls } from "./styles";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl bg-surface p-4 shadow-[0_1px_3px_rgba(46,49,39,0.12)] ${className}`}>{children}</section>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function ZipSelect({ value, onChange }: { value: string; onChange: (z: string) => void }) {
  return (
    <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
      {ZIP_OPTIONS.map((z) => (
        <option key={z.zip} value={z.zip}>
          {z.zip} {z.name}
        </option>
      ))}
    </select>
  );
}

export function BedsSelect({ value, onChange, any }: { value: string; onChange: (v: string) => void; any?: boolean }) {
  return (
    <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
      {any && <option value="">Any</option>}
      <option value="0">Studio</option>
      <option value="1">1 bedroom</option>
      <option value="2">2 bedrooms</option>
      <option value="3">3 bedrooms</option>
    </select>
  );
}

export function TriState({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">I don&apos;t know</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>
  );
}
export const triToBool = (v: string): boolean | null => (v === "yes" ? true : v === "no" ? false : null);

export function Disclaimer({ kind = "legal", text }: { kind?: "legal" | "estimate"; text?: string }) {
  return (
    <p className="rounded-lg bg-slate-100 px-3 py-2 text-xs leading-relaxed text-slate-600" role="note">
      {text ?? (kind === "legal" ? DISCLAIMER_LEGAL : DISCLAIMER_ESTIMATE)}
    </p>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{children}</p>;
}

export function Bar({ value, label }: { value: number; label: string }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-slate-700">{label}</span>
        <span className="font-semibold tabular-nums">{Math.round(v)}</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-200" role="meter" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-2.5 rounded-full bg-indigo-600" style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

export function MockBanner() {
  const on = useSyncExternalStore(subscribeMock, getMockSnapshot, () => false);
  if (!on) return null;
  return (
    <div className="bg-amber-100 px-4 py-2 text-center text-xs text-amber-900 print:hidden" role="status">
      Showing sample data: the live API is not connected, so these numbers are not real.
    </div>
  );
}

// Server pages render this to tell the banner their data came from fixtures.
export function MockFlag({ on }: { on: boolean }) {
  useEffect(() => {
    if (on) markMock();
  }, [on]);
  return null;
}
