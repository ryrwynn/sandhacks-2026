"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import ApartmentCard, { CardSkeletons } from "@/components/ApartmentCard";
import { selectCls, cardCls, btnGhostCls } from "@/components/styles";
import { useSaved, type SavedItem } from "@/lib/saved";
import { listingTitle } from "@/lib/tracker";

type Sort = "recent" | "price" | "drop";

const focusCls = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary";
// The mobile tab bar is 3.5rem tall plus the safe area; the bar and toast sit just above it.
const above = "bottom-[calc(3.5rem+env(safe-area-inset-bottom))] md:bottom-0";

export default function Saved() {
  const { items, listings, ready, loading, has, remove, restore } = useSaved();
  const [sort, setSort] = useState<Sort>("recent");

  const rows = useMemo(() => {
    const r = items.map((item) => ({ item, l: listings[item.id] })).filter((x) => x.l);
    if (sort === "price") r.sort((a, b) => a.l.current_price_usd - b.l.current_price_usd);
    if (sort === "drop") r.sort((a, b) => (a.l.current_price_usd - a.item.priceAtSave) - (b.l.current_price_usd - b.item.priceAtSave));
    return r;   // "recent": items are stored newest first
  }, [items, listings, sort]);

  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [blocked, setBlocked] = useState<{ id: number; title: string }[]>([]);
  const [undo, setUndo] = useState<{ removed: SavedItem[]; before: SavedItem[] } | null>(null);
  const anchor = useRef<number | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Only apartments still shown count as selected.
  const chosen = useMemo(() => rows.filter((r) => selected.has(r.item.id)), [rows, selected]);
  const n = chosen.length;

  const pick = useCallback((id: number, range: boolean) => {
    setBlocked([]);
    const ids = rows.map((r) => r.item.id);
    const a = anchor.current;
    setSelected((cur) => {
      const next = new Set(cur);
      if (range && a != null && ids.includes(a) && ids.includes(id)) {
        const [i, j] = [ids.indexOf(a), ids.indexOf(id)].sort((x, y) => x - y);
        ids.slice(i, j + 1).forEach((x) => next.add(x));
      } else if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    if (!(range && a != null)) anchor.current = id;
  }, [rows]);

  const clear = useCallback(() => { setSelected(new Set()); setBlocked([]); anchor.current = null; }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (selected.size || blocked.length) clear();
      else if (selectMode) setSelectMode(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, blocked, selectMode, clear]);

  useEffect(() => () => { if (undoTimer.current) clearTimeout(undoTimer.current); }, []);

  function onCardClick(e: MouseEvent<HTMLDivElement>, id: number) {
    const t = e.target as HTMLElement;
    if (t.closest("[data-select-box]")) return;                         // the checkbox handles itself
    if (t.closest("button") || t.closest('a[target="_blank"]')) return; // card menu and external listing link keep working
    if (e.shiftKey || e.ctrlKey || e.metaKey || selectMode) {
      e.preventDefault();
      e.stopPropagation();
      pick(id, e.shiftKey);
    }
  }

  function openSelected() {
    const bad: { id: number; title: string }[] = [];
    for (const { item, l } of chosen) {
      // No "noopener" feature: with it window.open returns null even on success, so a block could not be told apart.
      const w = window.open(`/apartments/${item.id}`, "_blank");
      if (w) { try { w.opener = null; } catch { /* nothing to clear */ } }
      else bad.push({ id: item.id, title: listingTitle(l) });
    }
    setBlocked(bad);
  }

  function removeSelected() {
    const removed = items.filter((i) => selected.has(i.id) && listings[i.id]);
    if (!removed.length) return;
    const before = items;
    removed.forEach((i) => remove(i.id));
    clear();
    setUndo({ removed, before });
    if (undoTimer.current) clearTimeout(undoTimer.current);
    undoTimer.current = setTimeout(() => setUndo(null), 8000);
  }

  function undoRemove() {
    if (!undo) return;
    restore(undo.removed, undo.before);
    setUndo(null);
    if (undoTimer.current) clearTimeout(undoTimer.current);
  }

  return (
    <main className={`space-y-5 ${n || undo ? "pb-28" : ""}`}>
      <section className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Saved apartments</h1>
          <p className="text-muted">Apartments you are tracking. They are saved in this browser only.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {items.length > 1 && (
            <select aria-label="Sort saved apartments" className={selectCls} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="recent">Recently saved</option>
              <option value="price">Price: low to high</option>
              <option value="drop">Biggest drop since saved</option>
            </select>
          )}
          {rows.length > 0 && (
            <button type="button" aria-pressed={selectMode}
              onClick={() => { if (selectMode) clear(); setSelectMode(!selectMode); }}
              className={`inline-flex min-h-11 items-center rounded-lg border px-4 font-semibold ${focusCls} ${selectMode ? "border-primary bg-primary text-on-primary" : "border-line bg-surface text-ink hover:bg-slate-100"}`}>
              Select
            </button>
          )}
          <Link href="/find" className="inline-flex min-h-11 items-center rounded-lg bg-primary px-4 font-semibold text-on-primary hover:bg-primary-hover">+ Save apartment</Link>
        </div>
      </section>

      {!ready || (loading && rows.length === 0) ? (
        <CardSkeletons n={4} />
      ) : items.length === 0 ? (
        <div className={`${cardCls} p-8 text-center`}>
          <p className="text-lg font-semibold">Nothing saved yet.</p>
          <p className="mb-4 text-muted">Find apartments to start a watchlist.</p>
          <Link href="/find" className="inline-flex min-h-11 items-center rounded-lg bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover">Find apartments</Link>
        </div>
      ) : (
        <>
          {selectMode && (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={`${btnGhostCls} min-h-11`} onClick={() => { setSelected(new Set(rows.map((r) => r.item.id))); setBlocked([]); }}>Select all</button>
              {n > 0 && <button type="button" className={`${btnGhostCls} min-h-11`} onClick={clear}>Clear</button>}
              <p className="text-sm text-muted">Shift-click selects a range. Press Escape to clear.</p>
            </div>
          )}
          {blocked.length > 0 && (
            <div role="alert" className={`${cardCls} p-4`} data-testid="saved-blocked-links">
              <p className="font-semibold">Your browser blocked {blocked.length === 1 ? "this tab" : `${blocked.length} tabs`}. Open {blocked.length === 1 ? "it" : "them"} by hand:</p>
              <ul className="mt-2">
                {blocked.map((b) => (
                  <li key={b.id}>
                    <a href={`/apartments/${b.id}`} target="_blank" rel="noopener noreferrer"
                      className={`flex min-h-11 items-center font-medium text-primary underline ${focusCls}`}>{b.title}</a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rows.map(({ item, l }) => {
              const on = selected.has(item.id);
              return (
                <div key={item.id} data-testid="saved-card" data-id={item.id} data-selected={on} aria-selected={on}
                  onClickCapture={(e) => onCardClick(e, item.id)}
                  className={`relative rounded-xl ${on ? "ring-2 ring-primary" : ""}`}>
                  <ApartmentCard listing={l} saved={has(item.id)} sinceSaved={item.priceAtSave}
                    note={item.example ? "Example: remove anytime" : undefined} onRemove={() => remove(item.id)} />
                  {selectMode && (
                    <label data-select-box className="absolute left-1 top-1 z-10 flex size-11 cursor-pointer items-center justify-center rounded-lg bg-surface/90 shadow">
                      <input type="checkbox" checked={on} onChange={() => {}} onClick={(e) => pick(item.id, e.shiftKey)}
                        aria-label={`Select ${listingTitle(l)}`}
                        className={`size-6 cursor-pointer accent-primary ${focusCls}`} />
                    </label>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
      {ready && items.length > 0 && rows.length < items.length && !loading && (
        <p className="text-sm text-muted">{items.length - rows.length} saved apartment{items.length - rows.length === 1 ? " is" : "s are"} no longer in our data and can&apos;t be shown.</p>
      )}

      {n > 0 && (
        <div role="region" aria-label="Selected apartments" data-testid="saved-action-bar"
          className={`fixed inset-x-0 ${above} z-30 border-t border-line bg-surface shadow-[0_-2px_8px_rgba(46,49,39,0.12)]`}>
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-2">
            <span className="mr-auto font-semibold">{n} selected</span>
            <button type="button" onClick={openSelected} className={`${btnGhostCls} min-h-11 ${focusCls}`}>Open selected in new tabs</button>
            <button type="button" onClick={removeSelected} className={`${btnGhostCls} min-h-11 ${focusCls}`}>Remove selected</button>
            <button type="button" onClick={clear} className={`${btnGhostCls} min-h-11 ${focusCls}`}>Clear</button>
          </div>
        </div>
      )}
      {undo && (
        <div role="status" aria-live="polite" data-testid="saved-undo-toast"
          className={`fixed inset-x-4 ${above} z-40 mx-auto ${n ? "mb-24 sm:mb-16" : "mb-2"} flex max-w-md items-center justify-between gap-3 rounded-xl bg-ink px-4 py-2 text-surface shadow-lg`}>
          <span>Removed {undo.removed.length} saved apartment{undo.removed.length === 1 ? "" : "s"}.</span>
          <button type="button" onClick={undoRemove}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg px-3 font-semibold underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-surface">Undo</button>
        </div>
      )}
    </main>
  );
}
