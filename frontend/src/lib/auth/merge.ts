import type { SavedItem } from "@/lib/saved";

/** The API's shape (contracts SavedItem). */
export type RemoteSave = { listing_id: number; saved_at: string; price_at_save: number | null; target: number | null };

export type MergeResult = {
  local: SavedItem[];       // what localStorage should hold
  remote: RemoteSave[];     // what the server should hold
  changedLocal: boolean;
  changedRemote: boolean;
};

const toRemote = (i: SavedItem): RemoteSave => ({
  listing_id: i.id, saved_at: i.savedAt, price_at_save: Math.round(i.priceAtSave), target: i.target == null ? null : Math.round(i.target),
});
const sig = (r: RemoteSave[]) =>
  JSON.stringify([...r].sort((a, b) => a.listing_id - b.listing_id).map((x) => [x.listing_id, new Date(x.saved_at).getTime(), x.price_at_save, x.target]));
const sameTime = (a: string, b: string) => new Date(a).getTime() === new Date(b).getTime();

/**
 * Union of this browser's saves and the server's.
 * - Example apartments (seeded on a first visit) are never uploaded.
 * - An id that was synced before but is gone locally was removed on purpose: it is dropped from the server too.
 * - On a clash the earlier saved_at wins and the local target wins when one is set.
 */
export function mergeSaves(local: SavedItem[], remote: RemoteSave[], lastSynced: number[]): MergeResult {
  const localIds = new Set(local.map((i) => i.id));
  const deleted = new Set(lastSynced.filter((id) => !localIds.has(id)));
  const out = new Map<number, SavedItem>();
  for (const r of remote) {
    if (deleted.has(r.listing_id)) continue;
    out.set(r.listing_id, { id: r.listing_id, savedAt: r.saved_at, priceAtSave: r.price_at_save ?? 0, target: r.target });
  }
  for (const l of local) {
    if (l.example) continue;
    const prev = out.get(l.id);
    out.set(l.id, prev
      ? { ...l, savedAt: new Date(prev.savedAt) < new Date(l.savedAt) ? prev.savedAt : l.savedAt, target: l.target !== undefined ? l.target : prev.target }
      : l);
  }
  const merged = [...out.values()].sort((a, b) => +new Date(b.savedAt) - +new Date(a.savedAt));
  const examples = local.filter((l) => l.example && !out.has(l.id) && merged.length === 0);
  const nextLocal = [...merged, ...examples];

  const nextRemote = merged.map(toRemote);
  const localReal = local.filter((l) => !l.example);
  const changedLocal =
    merged.length !== localReal.length ||
    merged.some((m) => {
      const l = localReal.find((x) => x.id === m.id);
      return !l || !sameTime(l.savedAt, m.savedAt) || (l.target ?? null) !== (m.target ?? null);
    });
  return { local: nextLocal, remote: nextRemote, changedLocal, changedRemote: sig(nextRemote) !== sig(remote) };
}
