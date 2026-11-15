import type { Metadata } from "next";
import { Suspense } from "react";
import LetterView from "@/components/LetterView";
import type { Lang } from "@/lib/contract";

export const metadata: Metadata = { title: "Reply letter | RentOrKnot" };

const LANGS: Lang[] = ["en", "es", "vi", "tl"];

async function Letter({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ lang?: string }> }) {
  const { id } = await params;
  const { lang } = await searchParams;
  const initial = LANGS.find((l) => l === lang) ?? "en";
  return <LetterView id={id} initialLang={initial} />;
}

export default function LetterPage(props: PageProps<"/renter/letter/[id]">) {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-bold print:hidden">Your reply letter</h1>
      <Suspense fallback={<p className="text-sm text-slate-600">Loading...</p>}>
        <Letter params={props.params} searchParams={props.searchParams as Promise<{ lang?: string }>} />
      </Suspense>
    </main>
  );
}
