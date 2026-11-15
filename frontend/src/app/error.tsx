"use client";
import Link from "next/link";

/** Shown when a page can't load its data (the API is down or answered with an error). Never sample numbers. */
export default function PageError({ retry }: { error: unknown; retry: () => void }) {
  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">We couldn&apos;t load this page</h1>
      <p className="text-muted">Our data service didn&apos;t answer. This is usually brief, for example while the site updates.</p>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={() => retry()}
          className="min-h-11 rounded-lg bg-primary px-5 font-semibold text-on-primary hover:bg-primary-hover">
          Try again
        </button>
        <Link href="/" className="inline-flex min-h-11 items-center rounded-lg px-3 font-medium text-accent-strong underline underline-offset-2">
          Back to the market overview
        </Link>
      </div>
    </main>
  );
}
