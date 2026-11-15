"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import Map, { Layer, NavigationControl, Source, type MapMouseEvent, type MapRef } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";
import type { ZipSummary } from "@/lib/contract";
import { pct, rentOf, usd } from "@/lib/format";
import { getGeoZips } from "@/lib/night-api";
import AreaSearch from "./AreaSearch";
import AddArea from "./AddArea";

type Props = {
  /** Mapbox public token (pk...), read on the server at request time. Missing or invalid: a ranked list is shown. */
  token: string | null;
  zips: ZipSummary[];
  /** ZIPs to outline (finder results). */
  highlight?: string[];
  /** Zoom to this ZIP (profile page). */
  focus?: string;
  heightClass?: string;
  /** Home page: area search and "Add this area" under the map, and geometry that loads as the map moves. */
  explore?: boolean;
};

/** ZIP of a feature: our files use `zip`; Census files use ZCTA5CE20 or GEOID20. */
const zipOf = (f: GeoJSON.Feature) => { const p = (f.properties ?? {}) as Record<string, unknown>; return String(p.zip ?? p.ZCTA5CE20 ?? p.GEOID20 ?? p.GEOID ?? ""); };

const SCALE = ["#ffe8d6", "#ddbea9", "#cb997e", "#8f5a3f"];

export const validToken = (t: string | null | undefined): t is string => !!t && t.startsWith("pk.");

function forecastText(z: ZipSummary) {
  return z.rent_forecast_change_pct == null ? "no forecast" : `${pct(z.rent_forecast_change_pct, 1, true)} rent in 12 months`;
}

export default function ZipMap(props: Props) {
  if (validToken(props.token)) return <MapView {...props} token={props.token} />;
  return (
    <div className="space-y-3">
      {props.explore && <AreaSearch />}
      <ZipList zips={props.zips} highlight={props.highlight} />
    </div>
  );
}

function Legend({ min, max }: { min: number; max: number }) {
  return (
    <div className="rounded-lg bg-surface/95 p-2 text-xs shadow" aria-label="Legend: typical monthly rent">
      <div className="mb-1 font-medium text-slate-700">Typical monthly rent</div>
      <div className="flex h-2.5 w-36 overflow-hidden rounded">
        {SCALE.map((c) => (
          <div key={c} className="flex-1" style={{ background: c }} />
        ))}
      </div>
      <div className="mt-0.5 flex justify-between tabular-nums text-slate-600">
        <span>{usd(min)}</span>
        <span>{usd(max)}</span>
      </div>
    </div>
  );
}

function Detail({ z }: { z: ZipSummary }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl bg-surface px-3 py-2 text-base shadow-[0_1px_3px_rgba(46,49,39,0.12)]">
      <div>
        <div className="font-semibold">
          {z.zip} {z.name}
        </div>
        <div className="text-slate-600">
          {usd(rentOf(z))} typical rent, {forecastText(z)}
        </div>
      </div>
      <Link href={`/zip/${z.zip}`} className="shrink-0 font-medium text-accent-strong underline">
        Profile
      </Link>
    </div>
  );
}

function MapView({ token, zips, highlight = [], focus, heightClass = "h-72 sm:h-96", explore }: Props & { token: string }) {
  const ref = useRef<MapRef>(null);
  const [shapes, setShapes] = useState<GeoJSON.FeatureCollection | null>(null);
  const [active, setActive] = useState<string | null>(focus ?? null);
  const [failed, setFailed] = useState(false);
  const loadedFiles = useRef(new Set<string>());
  const moveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetch("/zips.geojson")
      .then((r) => r.json())
      .then(setShapes)
      .catch(() => setFailed(true));
  }, []);

  // Load county geometry as the viewport moves: ask GET /geo/zips which county files it needs, fetch any not yet loaded, merge by ZIP.
  const loadViewport = () => {
    const b = ref.current?.getBounds();
    if (!explore || !b) return;
    if (moveTimer.current) clearTimeout(moveTimer.current);
    moveTimer.current = setTimeout(async () => {
      try {
        const g = await getGeoZips([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
        for (const f of g.files) {
          if (loadedFiles.current.has(f.url) || !f.url.startsWith("/geo/")) continue;
          loadedFiles.current.add(f.url);
          const fc = await fetch(f.url).then((r) => (r.ok ? r.json() : null), () => null) as GeoJSON.FeatureCollection | null;
          if (!fc?.features) { loadedFiles.current.delete(f.url); continue; }
          setShapes((cur) => {
            const have = new Set((cur?.features ?? []).map(zipOf));
            const add = fc.features.filter((x) => zipOf(x) && !have.has(zipOf(x))).map((x) => ({ ...x, properties: { ...x.properties, zip: zipOf(x) } }));
            return { type: "FeatureCollection", features: [...(cur?.features ?? []), ...add] };
          });
        }
      } catch { /* geometry is optional: the base shapes stay */ }
    }, 500);
  };
  useEffect(() => () => { if (moveTimer.current) clearTimeout(moveTimer.current); }, []);

  const byZip = useMemo(() => Object.fromEntries(zips.map((z) => [z.zip, z])), [zips]);
  const rents = zips.map(rentOf).filter((x): x is number => x != null);
  const min = Math.min(...rents);
  const max = Math.max(...rents);

  const data = useMemo(() => {
    if (!shapes) return null;
    return {
      ...shapes,
      features: shapes.features.map((f) => {
        const zip = String((f.properties as { zip: string }).zip);
        const z = byZip[zip];
        return { ...f, properties: { zip, rent: z ? rentOf(z) ?? -1 : -1, hl: highlight.includes(zip) || zip === focus } };
      }),
    } as GeoJSON.FeatureCollection;
  }, [shapes, byZip, highlight, focus]);

  const fit = () => {
    if (!focus || !shapes || !ref.current) return;
    const f = shapes.features.find((x) => (x.properties as { zip: string }).zip === focus);
    if (!f) return;
    const pts = JSON.stringify(f.geometry).match(/-?\d+\.\d+,-?\d+\.\d+/g)?.map((p) => p.split(",").map(Number)) ?? [];
    if (!pts.length) return;
    const lngs = pts.map((p) => p[0]);
    const lats = pts.map((p) => p[1]);
    ref.current.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]], { padding: 24, duration: 0 });
  };
  useEffect(fit, [focus, shapes]);

  if (failed || !isFinite(min)) return <ZipList zips={zips} highlight={highlight} />;

  const stops = SCALE.flatMap((c, i) => [min + ((max - min) * i) / (SCALE.length - 1), c]);
  const onMove = (e: MapMouseEvent) => {
    const z = e.features?.[0]?.properties?.zip;
    if (z) setActive(String(z));
  };

  return (
    <div className="space-y-2">
      {explore && <AreaSearch onPick={(a) => ref.current?.flyTo({ center: [a.centroid_lng!, a.centroid_lat!], zoom: 11.5 })} />}
      <div className={`relative w-full overflow-hidden rounded-xl shadow-[0_1px_3px_rgba(46,49,39,0.2)] ${heightClass}`}>
        <Map
          ref={ref}
          mapboxAccessToken={token}
          initialViewState={{ longitude: -117.13, latitude: 32.76, zoom: 9.2 }}
          mapStyle="mapbox://styles/mapbox/light-v11"
          interactiveLayerIds={["zip-fill"]}
          onMouseMove={onMove}
          onClick={onMove}
          onLoad={() => { fit(); loadViewport(); }}
          onMoveEnd={loadViewport}
          cooperativeGestures
          style={{ width: "100%", height: "100%" }}
        >
          <NavigationControl showCompass={false} />
          {data && (
            <Source id="zips" type="geojson" data={data}>
              <Layer
                id="zip-fill"
                type="fill"
                paint={{
                  "fill-color": ["case", ["<", ["get", "rent"], 0], "#e9ddd2", ["interpolate", ["linear"], ["get", "rent"], ...stops]],
                  "fill-opacity": 0.85,
                }}
              />
              <Layer
                id="zip-line"
                type="line"
                paint={{
                  "line-color": ["case", ["get", "hl"], "#2e3127", "#8f5a3f"],
                  "line-width": ["case", ["get", "hl"], 3.5, 0.8],
                }}
              />
              <Layer
                id="zip-label"
                type="symbol"
                layout={{ "text-field": ["get", "zip"], "text-size": 11 }}
                paint={{ "text-color": "#2e3127", "text-halo-color": "#fffaf5", "text-halo-width": 1.2 }}
              />
            </Source>
          )}
        </Map>
        <div className="pointer-events-none absolute bottom-2 left-2">
          <Legend min={min} max={max} />
        </div>
      </div>
      {active && byZip[active] ? (
        <Detail z={byZip[active]} />
      ) : (
        <p className="text-sm text-slate-600">Hover or tap a ZIP to see its 12-month rent forecast.</p>
      )}
      {explore && <AddArea compact />}
    </div>
  );
}

/** No-map fallback: ZIPs ranked by typical rent, highest first, with shading chips and forecast change. */
export function ZipList({ zips, highlight = [] }: { zips: ZipSummary[]; highlight?: string[] }) {
  const sorted = [...zips].sort((a, b) => (rentOf(b) ?? 0) - (rentOf(a) ?? 0));
  return (
    <ol className="divide-y divide-line rounded-xl bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.12)]" aria-label="ZIP codes ranked by typical rent">
      {sorted.map((z, i) => (
        <li key={z.zip}>
          <Link href={`/zip/${z.zip}`} className={`flex items-center justify-between gap-3 px-3 py-3 min-h-11 ${highlight.includes(z.zip) ? "bg-amber-50" : ""}`}>
            <span className="flex items-center gap-3">
              <span className="w-5 text-right text-xs tabular-nums text-slate-500">{i + 1}</span>
              <span>
                <span className="block font-medium">
                  {z.zip} {z.name}
                </span>
                <span className="block text-xs text-slate-600">{forecastText(z)}</span>
              </span>
            </span>
            <span className="font-semibold tabular-nums">{usd(rentOf(z))}</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
