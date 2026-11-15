"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Market overview" },
  { href: "/saved", label: "Saved apartments" },
  { href: "/alerts", label: "Price alerts" },
  { href: "/find", label: "Find apartments" },
];

export default function NavBar() {
  const path = usePathname();
  return (
    <header className="nav">
      <Link href="/" className="brand">RentOrKnot</Link>
      <nav aria-label="Main">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""} aria-current={path === l.href ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
      </nav>
      <button className="ghost">My account</button>
    </header>
  );
}
