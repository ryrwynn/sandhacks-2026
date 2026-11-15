import type { Metadata } from "next";
import AreasBrowser from "@/components/AreasBrowser";

export const metadata: Metadata = { title: "Coverage | RentOrKnot" };

export default function AreasPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">Coverage</h1>
      <p className="text-muted">Where RentOrKnot has listings and prices. Missing a place? Add it and we show the cost estimate and queue.</p>
      <AreasBrowser />
    </main>
  );
}
