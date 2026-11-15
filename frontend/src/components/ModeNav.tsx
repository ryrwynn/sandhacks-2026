"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/renter", label: "Renter" },
  { href: "/buyer", label: "Buyer" },
  { href: "/owner", label: "Owner" },
  { href: "/about", label: "About" },
];

export default function ModeNav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur print:hidden">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-4 py-2">
        <Link href="/" className="text-lg font-bold text-indigo-800">RentOrKnot</Link>
        <nav aria-label="Main" className="flex gap-1">
          {LINKS.map((l) => {
            const active = path === l.href || path.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-lg px-3 py-2 text-sm font-medium ${active ? "bg-indigo-100 text-indigo-900" : "text-slate-700 hover:bg-slate-100"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
