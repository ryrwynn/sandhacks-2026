import type { Metadata } from "next";
import Link from "next/link";
import OwnerTools from "@/components/OwnerTools";

export const metadata: Metadata = { title: "Owner | RentOrKnot" };

export default function OwnerPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold">Owner tools</h1>
      <Link href="/owner/reach" className="inline-flex min-h-11 items-center font-semibold text-accent-strong underline underline-offset-2">Owner reach optimizer</Link>
      <OwnerTools />
    </main>
  );
}
