import Link from "next/link";

const link = "inline-flex min-h-11 items-center px-3 hover:text-ink hover:underline";

export default function SiteFooter() {
  return (
    <footer className="mx-auto w-full max-w-7xl px-4 pb-24 text-sm text-muted md:pb-6">
      <nav aria-label="Legal" className="flex flex-wrap items-center justify-center">
        <Link href="/privacy" className={link}>Privacy</Link>
        <span aria-hidden>·</span>
        <Link href="/terms" className={link}>Terms</Link>
        <span aria-hidden>·</span>
        <Link href="/about" className={link}>About</Link>
      </nav>
    </footer>
  );
}
