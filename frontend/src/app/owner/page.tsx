import type { Metadata } from "next";
import OwnerTools from "@/components/OwnerTools";

export const metadata: Metadata = { title: "Owner | RentOrKnot" };

export default function OwnerPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Owner tools</h1>
      <OwnerTools />
    </main>
  );
}
