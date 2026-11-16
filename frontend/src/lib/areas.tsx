"use client";
import { useEffect, useState } from "react";
import { getZips } from "./api";
import { ZIP_OPTIONS } from "./format";

export type Area = { zip: string; name: string; tier: "core" | "county" | "on_demand" };

/** The static 12: the first render and the fallback when /zips can't be read. */
const STATIC: Area[] = ZIP_OPTIONS.map((z) => ({ ...z, tier: "core" as const }));

let cache: Area[] | null = null;
let inflight: Promise<Area[]> | null = null;

function load(): Promise<Area[]> {
  if (cache) return Promise.resolve(cache);
  inflight ??= getZips()
    .then((r) => {
      const rows = r.zips.map((z) => ({ zip: z.zip, name: z.name, tier: z.tier }));
      if (rows.length) cache = rows;
      return cache ?? STATIC;
    })
    .catch(() => STATIC)
    .finally(() => { inflight = null; });
  return inflight;
}

/** Every served area (cached, from /zips). Starts as the static 12, so the first render never waits. */
export function useAreas(): Area[] {
  const [areas, setAreas] = useState<Area[]>(cache ?? STATIC);
  useEffect(() => {
    let live = true;
    load().then((a) => { if (live) setAreas(a); });
    return () => { live = false; };
  }, []);
  return areas;
}

const GROUPS: { tier: Area["tier"]; label: string }[] = [
  { tier: "core", label: "Core areas" },
  { tier: "county", label: "San Diego County" },
  { tier: "on_demand", label: "Added on request" },
];

/** The <option>s of an area picker, grouped and sorted by name, "Name (ZIP)". Put it inside a <select>. */
export function AreaOptions() {
  const areas = useAreas();
  return (
    <>
      {GROUPS.map((g) => {
        const rows = areas.filter((a) => a.tier === g.tier).sort((a, b) => a.name.localeCompare(b.name));
        return rows.length ? (
          <optgroup key={g.tier} label={g.label}>
            {rows.map((a) => <option key={a.zip} value={a.zip}>{a.name} ({a.zip})</option>)}
          </optgroup>
        ) : null;
      })}
    </>
  );
}
