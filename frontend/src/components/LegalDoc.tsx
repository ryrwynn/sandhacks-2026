import { Card } from "@/components/ui";

/** Shared layout for /privacy and /terms: one h1, the date, then short sections. */
export function LegalDoc({ title, intro, sections }: { title: string; intro: string; sections: { h: string; body: React.ReactNode }[] }) {
  return (
    <main className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-bold sm:text-2xl">{title}</h1>
      <p className="text-sm text-muted">Last updated: November 15, 2026</p>
      <p className="text-slate-700">{intro}</p>
      {sections.map((s) => (
        <Card key={s.h} className="space-y-2">
          <h2 className="text-lg font-bold">{s.h}</h2>
          <div className="space-y-2 break-words text-sm">{s.body}</div>
        </Card>
      ))}
    </main>
  );
}
