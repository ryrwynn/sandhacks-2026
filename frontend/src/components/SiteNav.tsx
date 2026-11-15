"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSaved } from "@/lib/saved";
import { DrawerButton } from "./ToolsSidebar";
import { Bell, ChartColumn, Heart, Search, type LucideIcon } from "lucide-react";
import Logo from "./brand/Logo";
import { AccountButton } from "./account/AccountButton";

const MAIN = [
  { href: "/", label: "Market overview", short: "Market", icon: ChartColumn },
  { href: "/saved", label: "Saved apartments", short: "Saved", icon: Heart },
  { href: "/alerts", label: "Price alerts", short: "Alerts", icon: Bell },
  { href: "/find", label: "Find apartments", short: "Find", icon: Search },
] as { href: string; label: string; short: string; icon: LucideIcon }[];

const isActive = (path: string, href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(href + "/"));

function Badge({ n, label }: { n: number; label: string }) {
  if (n <= 0) return null;
  return (
    <span className="ml-1.5 inline-flex min-w-5 items-center justify-center rounded-full bg-accent-strong px-1.5 text-xs font-semibold leading-5 text-on-primary" aria-label={label}>
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
          <Link href="/" aria-label="RentOrKnot home" className="mr-3 shrink-0"><Logo /></Link>
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
            <div id="account-button-slot" data-slot="account-button">
              <AccountButton />
            </div>
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
              <span className={`rounded-full px-4 py-0.5 ${on ? "bg-line" : ""}`}><l.icon size={22} strokeWidth={1.8} aria-hidden="true" /></span>
              <span>{l.short}</span>
              {counts[l.href] > 0 && (
                <span className="absolute right-[calc(50%-26px)] top-1 inline-flex min-w-5 items-center justify-center rounded-full bg-accent-strong px-1 text-xs font-semibold leading-5 text-on-primary" aria-label={countLabel[l.href]}>
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
