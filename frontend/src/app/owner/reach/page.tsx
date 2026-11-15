import type { Metadata } from "next";
import OwnerReach from "@/components/OwnerReach";

export const metadata: Metadata = { title: "Owner reach | RentOrKnot" };

export default function OwnerReachPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Owner reach optimizer</h1>
      <p className="text-muted">Estimate how many renters would shortlist your listing at a given rent, and what to change to reach more.</p>
      <OwnerReach />
    </main>
  );
}
