import type { Metadata } from "next";
import { AdvisorChat, MatchPanel } from "@/components/AdvisorPanel";

export const metadata: Metadata = { title: "Find by needs | RentOrKnot" };

export default function AdvisorPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Find by needs</h1>
      <p className="text-muted">Describe what you need in your own words, or ask the housing advisor a question.</p>
      <MatchPanel />
      <AdvisorChat />
    </main>
  );
}
