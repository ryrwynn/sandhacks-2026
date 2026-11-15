"use client";
import { useState } from "react";
import CheckForm from "./CheckForm";
import ListingForm from "./ListingForm";
import Finder from "./Finder";

const TABS = [
  { id: "check", label: "Check my increase" },
  { id: "listing", label: "Check a listing" },
  { id: "find", label: "Find a place" },
] as const;

export default function RenterTabs() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("check");
  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Renter tools" className="grid grid-cols-3 gap-1 rounded-xl bg-slate-200 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`min-h-11 rounded-lg px-1 text-sm font-medium leading-tight ${tab === t.id ? "bg-white text-indigo-900 shadow" : "text-slate-700"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "check" && <CheckForm />}
        {tab === "listing" && <ListingForm />}
        {tab === "find" && <Finder persona="starter" />}
      </div>
    </div>
  );
}
