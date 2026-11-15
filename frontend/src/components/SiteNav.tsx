"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useSaved } from "@/lib/saved";

const MAIN = [
  { href: "/", label: "Market overview", short: "Market", icon: "M4 19V9m6 10V5m6 14v-7m4 7H2" },
  { href: "/saved", label: "Saved apartments", short: "Saved", icon: "M12 20.5s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.9a4.3 4.3 0 0 1 7.5 2.6c0 5.4-7.5 10-7.5 10z" },
  { href: "/alerts", label: "Price alerts", short: "Alerts", icon: "M6 17V11a6 6 0 1 1 12 0v6l1.5 2h-15L6 17zm4 4h4" },
  { href: "/find", label: "Find apartments", short: "Find", icon: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm9 3-4.3-4.3" },
] as const;

const TOOLS = [
  { href: "/renter", label: "Rent increase check" },
  { href: "/buyer", label: "Buy" },
  { href: "/owner", label: "Own" },
  { href: "/about", label: "About" },
];

const isActive = (path: string, href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(href + "/"));

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function Badge({ n, label }: { n: number; label: string }) {
  if (n <= 0) return null;
  return (
    <span className="ml-1.5 inline-flex min-w-5 items-center justify-center rounded-full bg-accent-strong px-1.5 text-xs font-semibold leading-5 text-white" aria-label={label}>
      {n}
    </span>
  );
}

function ToolsMenu({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const active = TOOLS.some((t) => isActive(path, t.href));

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((o) => !o)}
        className={`flex min-h-11 items-center gap-1 rounded-lg px-3 text-sm font-medium ${active ? "text-ink" : "text-muted"} hover:text-ink`}
      >
        Tools
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
      </button>
      {open && (
        <ul className="absolute right-0 top-full z-30 mt-1 w-56 rounded-xl bg-surface p-1 shadow-[0_6px_24px_rgba(46,49,39,0.2)]">
          {TOOLS.map((t) => (
            <li key={t.href}>
              <Link
                href={t.href}
                onClick={() => setOpen(false)}
                aria-current={isActive(path, t.href) ? "page" : undefined}
                className={`flex min-h-11 items-center rounded-lg px-3 text-base hover:bg-bg ${isActive(path, t.href) ? "font-semibold" : ""}`}
              >
                {t.label}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SiteNav() {
  const path = usePathname();
  const { items, alertCount } = useSaved();
  const counts: Record<string, number> = { "/saved": items.length, "/alerts": alertCount };
  const countLabel: Record<string, string> = {
    "/saved": `${items.length} saved`,
    "/alerts": `${alertCount} apartments hit a target or changed price`,
  };

  return (
    <>
      <header className="no-print sticky top-0 z-20 bg-surface shadow-[0_1px_0_var(--line)]">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4">
          <Link href="/" className="mr-3 text-lg font-bold tracking-tight text-ink">RentOrKnot</Link>
          <nav aria-label="Main" className="hidden h-full flex-1 gap-1 md:flex">
            {MAIN.map((l) => {
              const on = isActive(path, l.href);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  aria-current={on ? "page" : undefined}
                  className={`flex items-center border-b-2 px-3 text-sm ${on ? "border-primary font-semibold text-ink" : "border-transparent text-muted hover:text-ink"}`}
                >
                  {l.label}
                  {counts[l.href] !== undefined && <Badge n={counts[l.href]} label={countLabel[l.href]} />}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto md:ml-0"><ToolsMenu path={path} /></div>
        </div>
      </header>

      <nav aria-label="Main" className="no-print fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 bg-surface pb-[env(safe-area-inset-bottom)] shadow-[0_-1px_0_var(--line)] md:hidden">
        {MAIN.map((l) => {
          const on = isActive(path, l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              aria-current={on ? "page" : undefined}
              aria-label={l.label}
              className={`relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs ${on ? "font-semibold text-ink" : "text-muted"}`}
            >
              <span className={`rounded-full px-4 py-0.5 ${on ? "bg-line" : ""}`}><Icon d={l.icon} /></span>
              <span>{l.short}</span>
              {counts[l.href] > 0 && (
                <span className="absolute right-[calc(50%-26px)] top-1 inline-flex min-w-5 items-center justify-center rounded-full bg-accent-strong px-1 text-xs font-semibold leading-5 text-white" aria-label={countLabel[l.href]}>
                  {counts[l.href]}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
