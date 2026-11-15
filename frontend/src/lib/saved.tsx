"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const KEY = "sandhacks:saved";
type Ctx = { ids: string[]; has: (id: string) => boolean; toggle: (id: string) => void };
const SavedCtx = createContext<Ctx>({ ids: [], has: () => false, toggle: () => {} });

export function SavedProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<string[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      setIds(raw ? JSON.parse(raw) : ["1", "2", "3", "4"]); // seeded for the demo
    } catch {}
  }, []);

  const toggle = (id: string) =>
    setIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      try { localStorage.setItem(KEY, JSON.stringify(next)); } catch {}
      return next;
    });

  return <SavedCtx.Provider value={{ ids, has: (id) => ids.includes(id), toggle }}>{children}</SavedCtx.Provider>;
}

export const useSaved = () => useContext(SavedCtx);
