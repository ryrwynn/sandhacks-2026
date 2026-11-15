"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getListings, getListingsByIds, isMock } from "./api";
import type { ListingSummary } from "./tracker";

/**
 * The watchlist lives only in this browser's localStorage: nothing about it is sent to the server.
 * Every read and write is wrapped in try/catch, so the app works when storage is empty or blocked
 * (the list then lasts until the tab closes).
 */
const KEY = "rentorknot:saved:v1";

export type SavedItem = {
  id: number;
  savedAt: string;          // ISO time
  priceAtSave: number;
  target?: number | null;   // alert target rent
  seenPrice?: number;       // the price when the alerts page last showed this one as seen
  example?: boolean;        // seeded on first visit; marked "Example: remove anytime"
};

export type AlertKind = "target" | "changed";

/** Why a saved apartment is on the alerts page, or null. Target hits come first. */
export function alertOf(item: SavedItem, l: ListingSummary | undefined): AlertKind | null {
  if (!l) return null;
  const price = l.current_price_usd;
  if (item.target != null && price <= item.target) return "target";
  if (price !== (item.seenPrice ?? item.priceAtSave)) return "changed";
  return null;
}

type Stored = { items: SavedItem[]; seeded: boolean };

function read(): Stored | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const j = JSON.parse(raw) as Stored;
    if (!Array.isArray(j.items)) return null;
    return { items: j.items.filter((x) => typeof x?.id === "number" && typeof x.priceAtSave === "number"), seeded: !!j.seeded };
  } catch {
    return null;
  }
}
function write(s: Stored) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage blocked or full: keep going in memory */ }
}

type Ctx = {
  ready: boolean;                              // storage has been read (false during server render)
  items: SavedItem[];                          // newest first
  listings: Record<number, ListingSummary>;    // current data for saved ids
  loading: boolean;
  sample: boolean;                             // the listing data came from sample fixtures
  has: (id: number) => boolean;
  toggle: (l: ListingSummary) => void;
  remove: (id: number) => void;
  setTarget: (id: number, target: number | null) => void;
  markSeen: (id: number) => void;
  alertCount: number;
};

const SavedCtx = createContext<Ctx>({
  ready: false, items: [], listings: {}, loading: false, sample: false,
  has: () => false, toggle: () => {}, remove: () => {}, setTarget: () => {}, markSeen: () => {}, alertCount: 0,
});

export function SavedProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState<SavedItem[]>([]);
  const [listings, setListings] = useState<Record<number, ListingSummary>>({});
  const [loading, setLoading] = useState(false);
  const [sample, setSample] = useState(false);
  const seeded = useRef(false);

  const commit = useCallback((next: SavedItem[]) => {
    seeded.current = true;
    setItems(next);
    write({ items: next, seeded: true });
  }, []);

  // Read storage once, then on a first visit seed four real apartments with at least three observations.
  useEffect(() => {
    let cancelled = false;
    const stored = read();
    if (stored) {
      seeded.current = stored.seeded;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setItems(stored.items);
      setReady(true);
      return;
    }
    setReady(true);
    (async () => {
      try {
        const res = await getListings({ limit: 12, minObservations: 3, sort: "recent" });
        if (cancelled) return;
        const picks = res.items
          .filter((l) => l.listing_type === "rent" && l.active && l.n_observations >= 3)
          .sort((a, b) => b.n_observations - a.n_observations)
          .slice(0, 4);
        const now = new Date().toISOString();
        const seed = picks.map<SavedItem>((l) => ({ id: l.id, savedAt: now, priceAtSave: l.current_price_usd, example: true }));
        setItems((cur) => (cur.length ? cur : seed));
        // Sample fixtures are never persisted as the user's watchlist: real ones are seeded when the API answers.
        if (!isMock(res) && seed.length && !seeded.current) write({ items: seed, seeded: true });
      } catch { /* API down: start empty */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // Current data for the saved ids, refreshed when the set of ids changes.
  const idKey = items.map((i) => i.id).join(",");
  useEffect(() => {
    if (!ready || !idKey) return;
    let cancelled = false;
    setLoading(true);
    getListingsByIds(idKey.split(",").map(Number))
      .then((res) => {
        if (cancelled) return;
        setSample(isMock(res));
        setListings((cur) => ({ ...cur, ...Object.fromEntries(res.items.map((l) => [l.id, l])) }));
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ready, idKey]);

  const value = useMemo<Ctx>(() => {
    const has = (id: number) => items.some((i) => i.id === id);
    const remove = (id: number) => commit(items.filter((i) => i.id !== id));
    return {
      ready, items, listings, loading, sample, has, remove,
      toggle: (l) =>
        has(l.id)
          ? remove(l.id)
          : commit([{ id: l.id, savedAt: new Date().toISOString(), priceAtSave: l.current_price_usd }, ...items]),
      setTarget: (id, target) => commit(items.map((i) => (i.id === id ? { ...i, target } : i))),
      markSeen: (id) => {
        const l = listings[id];
        if (l) commit(items.map((i) => (i.id === id ? { ...i, seenPrice: l.current_price_usd } : i)));
      },
      alertCount: items.filter((i) => alertOf(i, listings[i.id])).length,
    };
  }, [ready, items, listings, loading, sample, commit]);

  return <SavedCtx.Provider value={value}>{children}</SavedCtx.Provider>;
}

export const useSaved = () => useContext(SavedCtx);
