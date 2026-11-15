import type { Metadata } from "next";
import ScenarioTool from "@/components/ScenarioTool";

export const metadata: Metadata = { title: "Forecast scenarios | RentOrKnot" };

export default function ScenariosPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Forecast scenarios</h1>
      <p className="text-muted">See how a ZIP&apos;s rent or home value could move under baseline, recession and growth assumptions.</p>
      <ScenarioTool />
    </main>
  );
}
