"use client";
import { useEffect, useState } from "react";
import { Check, Palette } from "lucide-react";
import { THEMES, THEME_KEY, type ThemeId } from "@/lib/theme";

function apply(id: ThemeId) {
  document.documentElement.setAttribute("data-theme", id);
  try { localStorage.setItem(THEME_KEY, id); } catch { /* storage blocked: the choice lasts this visit */ }
  window.dispatchEvent(new Event("rok-theme"));
}

function useTheme() {
  const [id, setId] = useState<ThemeId>("desert-clay");
  useEffect(() => {
    const read = () => setId((document.documentElement.getAttribute("data-theme") as ThemeId) || "desert-clay");
    read();
    window.addEventListener("rok-theme", read);
    return () => window.removeEventListener("rok-theme", read);
  }, []);
  return id;
}

/** Full list for the expanded sidebar and the drawer; one cycle button when the rail is collapsed. */
export default function ThemeSwitcher({ compact = false }: { compact?: boolean }) {
  const current = useTheme();
  if (compact) {
    const next = THEMES[(THEMES.findIndex((t) => t.id === current) + 1) % THEMES.length];
    return (
      <button type="button" onClick={() => apply(next.id)} title={`Theme: ${THEMES.find((t) => t.id === current)?.name}. Switch to ${next.name}`}
        aria-label={`Switch theme to ${next.name}`}
        className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-muted hover:bg-bg hover:text-ink">
        <Palette size={20} aria-hidden="true" />
      </button>
    );
  }
  return (
    <fieldset className="min-w-0 border-0 p-0">
      <legend className="mb-1 flex items-center gap-2 px-3 text-xs font-semibold uppercase tracking-wide text-muted"><Palette size={14} aria-hidden="true" /> Theme</legend>
      <ul className="space-y-0.5">
        {THEMES.map((t) => {
          const on = t.id === current;
          return (
            <li key={t.id}>
              <button type="button" onClick={() => apply(t.id)} aria-pressed={on}
                className={`flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-left text-sm hover:bg-bg ${on ? "bg-bg font-semibold text-ink" : "text-muted"}`}>
                <span className="flex shrink-0 overflow-hidden rounded-full border border-line" aria-hidden="true">
                  {t.swatch.map((c) => <span key={c} className="h-5 w-3" style={{ background: c }} />)}
                </span>
                <span className="min-w-0 flex-1 truncate">{t.name}</span>
                {on && <Check size={16} aria-hidden="true" className="shrink-0" />}
              </button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
