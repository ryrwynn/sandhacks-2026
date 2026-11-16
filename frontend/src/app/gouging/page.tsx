import type { Metadata } from "next";
import GougingCheck from "@/components/GougingCheck";

export const metadata: Metadata = { title: "Emergency Rent Limits | RentOrKnot" };

export default function GougingPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">Emergency Rent Limits</h1>
      <p className="text-muted">After a declared emergency, California Penal Code 396 limits rent increases. Enter a price to see whether it is over the limit.</p>
      <GougingCheck />
    </main>
  );
}
