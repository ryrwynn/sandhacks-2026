"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Building, ChartLine, House, Info, MapPinned, Menu, PanelLeftClose, PanelLeftOpen, ShieldCheck, Siren, Sparkles, Target, Wrench, X,
  type LucideIcon,
} from "lucide-react";

export const TOOLS: { href: string; label: string; hint: string; icon: LucideIcon }[] = [
  { href: "/renter", label: "Rent increase check", hint: "AB 1482 cap", icon: ShieldCheck },
  { href: "/gouging", label: "Gouging check", hint: "Emergency price limits", icon: Siren },
  { href: "/scenarios", label: "Forecast scenarios", hint: "Recession and growth", icon: ChartLine },
  { href: "/advisor", label: "Find by needs", hint: "Advisor and matching", icon: Sparkles },
  { href: "/owner/reach", label: "Owner reach", hint: "Who would shortlist it", icon: Target },
  { href: "/buyer", label: "Buy", hint: "Wealth builder", icon: House },
  { href: "/owner", label: "Own", hint: "Pricing and listing tools", icon: Building },
  { href: "/areas", label: "Coverage", hint: "Areas and add an area", icon: MapPinned },
  { href: "/about", label: "About", hint: "Method and limits", icon: Info },
];

type Ctx = { drawer: boolean; setDrawer: (b: boolean) => void; collapsed: boolean; toggleCollapsed: () => void };
const SidebarCtx = createContext<Ctx>({ drawer: false, setDrawer: () => {}, collapsed: false, toggleCollapsed: () => {} });
const KEY = "rok.sidebar.collapsed";

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    try { setCollapsed(localStorage.getItem(KEY) === "1"); } catch { /* storage blocked: stay expanded */ }
  }, []);
  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      try { localStorage.setItem(KEY, c ? "0" : "1"); } catch { /* ignore */ }
      return !c;
    });
  }, []);
  const v = useMemo(() => ({ drawer, setDrawer, collapsed, toggleCollapsed }), [drawer, collapsed, toggleCollapsed]);
  return <SidebarCtx.Provider value={v}>{children}</SidebarCtx.Provider>;
}

const isActive = (path: string, href: string) => path === href || path.startsWith(href + "/");

/** Header button: opens the drawer on phones. Hidden on desktop, where the sidebar is always there. */
export function DrawerButton() {
  const { drawer, setDrawer } = useContext(SidebarCtx);
  return (
    <button
      type="button"
      aria-label="Open tools"
      aria-expanded={drawer}
      aria-controls="tools-drawer"
      onClick={() => setDrawer(true)}
      className="flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-sm font-medium text-muted hover:text-ink md:hidden"
    >
      <Menu size={20} aria-hidden="true" /> Tools
    </button>
  );
}

function ToolLinks({ path, collapsed, onNavigate }: { path: string; collapsed: boolean; onNavigate?: () => void }) {
  // Longest matching href wins so /owner/reach does not also light up /owner.
  const best = TOOLS.filter((t) => isActive(path, t.href)).sort((a, b) => b.href.length - a.href.length)[0]?.href;
  return (
    <ul className="space-y-0.5">
      {TOOLS.map((t) => {
        const on = t.href === best;
        const I = t.icon;
        return (
          <li key={t.href}>
            <Link
              href={t.href}
              onClick={onNavigate}
              aria-current={on ? "page" : undefined}
              title={collapsed ? t.label : undefined}
              className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm hover:bg-bg ${on ? "bg-bg font-semibold text-ink" : "text-muted"} ${collapsed ? "justify-center px-0" : ""}`}
            >
              <I size={20} aria-hidden="true" className="shrink-0" />
              {collapsed ? <span className="sr-only">{t.label}</span> : (
                <span className="min-w-0">
                  <span className="block truncate">{t.label}</span>
                  <span className="block truncate text-xs font-normal text-muted">{t.hint}</span>
                </span>
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** Desktop: a sticky, collapsible rail. Phones: a drawer opened from the header. */
export function ToolsSidebar() {
  const path = usePathname();
  const { drawer, setDrawer, collapsed, toggleCollapsed } = useContext(SidebarCtx);

  useEffect(() => {
    if (!drawer) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setDrawer(false); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [drawer, setDrawer]);

  return (
    <>
      <aside
        aria-label="Tools"
        className={`no-print sticky top-14 hidden h-[calc(100vh-3.5rem)] shrink-0 overflow-y-auto border-r border-line bg-surface py-3 md:block ${collapsed ? "w-14 px-1" : "w-60 px-2"}`}
      >
        <div className={`mb-2 flex items-center ${collapsed ? "justify-center" : "justify-between px-3"}`}>
          {!collapsed && <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted"><Wrench size={14} aria-hidden="true" /> Tools</span>}
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand tools sidebar" : "Collapse tools sidebar"}
            aria-pressed={collapsed}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-muted hover:bg-bg hover:text-ink"
          >
            {collapsed ? <PanelLeftOpen size={20} aria-hidden="true" /> : <PanelLeftClose size={20} aria-hidden="true" />}
          </button>
        </div>
        <nav aria-label="Tools"><ToolLinks path={path} collapsed={collapsed} /></nav>
      </aside>

      {drawer && (
        <div className="no-print fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Tools" id="tools-drawer">
          <button type="button" aria-label="Close tools" className="absolute inset-0 bg-ink/40" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 flex w-[min(20rem,85vw)] flex-col bg-surface p-3 shadow-xl">
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-lg font-bold">Tools</span>
              <button type="button" aria-label="Close tools" onClick={() => setDrawer(false)} className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-muted hover:bg-bg">
                <X size={20} aria-hidden="true" />
              </button>
            </div>
            <nav aria-label="Tools" className="flex-1 overflow-y-auto"><ToolLinks path={path} collapsed={false} onNavigate={() => setDrawer(false)} /></nav>
          </div>
        </div>
      )}
    </>
  );
}
