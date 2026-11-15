import type { Metadata } from "next";
import { Suspense } from "react";
import ApartmentView from "@/components/ApartmentView";

export const metadata: Metadata = { title: "Apartment | RentOrKnot" };

async function Apartment({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ApartmentView id={id} />;
}

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="space-y-4"><div className="skeleton h-28" /><div className="skeleton h-80" /></div>}>
      <Apartment params={params} />
    </Suspense>
  );
}
