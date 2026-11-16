import type { Metadata } from "next";
import { Suspense } from "react";
import { AdvisorChat, MatchPanel } from "@/components/AdvisorPanel";

export const metadata: Metadata = { title: "Find by needs | RentOrKnot" };

export default function AdvisorPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">Find by needs</h1>
      <p className="text-muted">Describe what you need in your own words, or ask the housing advisor a question.</p>
      <Suspense fallback={<div className="skeleton h-72" />}>
        <MatchPanel />
        <AdvisorChat />
      </Suspense>
    </main>
  );
}
