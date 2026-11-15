import { Suspense } from "react";
import { getZips, isMock } from "@/lib/api";
import { mapboxToken } from "@/lib/server";
import MarketOverview from "@/components/MarketOverview";
import ZipMap from "@/components/ZipMap";
import { MockFlag } from "@/components/ui";

async function MapSection() {
  const token = await mapboxToken();
  const zips = await getZips();
  return (
    <>
      <MockFlag on={isMock(zips)} />
      <ZipMap token={token} zips={zips.zips} explore />
    </>
  );
}

export default function Home() {
  return (
    <MarketOverview
      map={
        <Suspense fallback={<div className="skeleton h-72" aria-label="Loading map" />}>
          <MapSection />
        </Suspense>
      }
    />
  );
}
