"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSaved } from "@/lib/saved";
import { DrawerButton } from "./ToolsSidebar";

const MAIN = [
  { href: "/", label: "Market overview", short: "Market", icon: "M4 19V9m6 10V5m6 14v-7m4 7H2" },
  { href: "/saved", label: "Saved apartments", short: "Saved", icon: "M12 20.5s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.9a4.3 4.3 0 0 1 7.5 2.6c0 5.4-7.5 10-7.5 10z" },
  { href: "/alerts", label: "Price alerts", short: "Alerts", icon: "M6 17V11a6 6 0 1 1 12 0v6l1.5 2h-15L6 17zm4 4h4" },
  { href: "/find", label: "Find apartments", short: "Find", icon: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm9 3-4.3-4.3" },
] as const;

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
          <div className="ml-auto flex items-center gap-1 md:ml-0">
            <DrawerButton />
            {/* ACCOUNT BUTTON SLOT (night-accounts): render <AccountButton/> from "@/components/account/AccountButton" here, replacing this empty container. */}
            <div id="account-button-slot" data-slot="account-button" />
          </div>
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
