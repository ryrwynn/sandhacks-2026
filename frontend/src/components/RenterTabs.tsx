"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import CheckForm from "./CheckForm";
import ListingForm from "./ListingForm";

const TABS = [
  { id: "check", label: "Check my increase" },
  { id: "listing", label: "Check a listing" },
] as const;

export type Prefill = { address: string; zip: string; year: string };

export default function RenterTabs({ prefill }: { prefill?: Prefill }) {
  const q = useSearchParams();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>(q.get("tab") === "listing" ? "listing" : "check");
  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Renter tools" className="grid grid-cols-2 gap-1 rounded-xl bg-slate-200 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`min-h-11 rounded-lg px-1 text-sm font-medium leading-tight ${tab === t.id ? "bg-surface text-indigo-900 shadow" : "text-slate-700"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "check" && <CheckForm prefill={prefill} />}
        {tab === "listing" && <ListingForm />}
      </div>
    </div>
  );
}
