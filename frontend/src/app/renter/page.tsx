import type { Metadata } from "next";
import RenterTabs from "@/components/RenterTabs";

export const metadata: Metadata = { title: "Renter | RentOrKnot" };

export default function RenterPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Renter tools</h1>
      <RenterTabs />
    </main>
  );
}
