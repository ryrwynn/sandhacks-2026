// Links that open a form with its fields filled in. Built only from the shared prefill table
// (lib/prefill.ts, generated from contracts/prefill.py): unknown forms or parameters are rejected.
// A link only fills fields; the person reads it and presses submit themselves. Nothing is sent from here.
import { PREFILL, type PrefillForm } from "@/lib/prefill";

export type PrefillLink = { form: string; url: string; button: string };

const BUTTONS: Record<PrefillForm, string> = {
  renter: "Open the rent check with these numbers",
  listing: "Open the price check with these numbers",
  gouging: "Open the emergency rent limit check with these numbers",
  owner: "Open the owner price check with these numbers",
  owner_reach: "Open the owner reach tool with these numbers",
  buyer: "Open the buyer tool with these numbers",
  find: "Open Find with these filters",
  advisor: "Open Find by needs with this description",
};

export const PREFILL_FORMS = Object.keys(PREFILL) as [PrefillForm, ...PrefillForm[]];

export function prefillLink(form: string, values: Record<string, string | number | boolean | null | undefined> = {}): PrefillLink {
  if (!(form in PREFILL)) throw new Error(`Unknown form ${form}. Forms: ${PREFILL_FORMS.join(", ")}`);
  const spec = PREFILL[form as PrefillForm] as { path: string; params: Record<string, string>; fixed?: Record<string, string> };
  const bad = Object.keys(values).filter((k) => !(k in spec.params));
  if (bad.length) throw new Error(`${form} has no prefill parameter ${bad.join(", ")}. Valid: ${Object.keys(spec.params).join(", ")}`);
  const q = new URLSearchParams(spec.fixed ?? {});
  for (const [k, v] of Object.entries(values)) {
    if (v === null || v === undefined || v === "") continue;
    q.set(k, typeof v === "boolean" ? (v ? "yes" : "no") : String(v));
  }
  const qs = q.toString();
  return { form, url: spec.path + (qs ? `?${qs}` : ""), button: BUTTONS[form as PrefillForm] };
}

/** Buttons for the answer: every prefill_form result among the run's tool results, once each. */
export function linksFromResults(results: unknown[]): PrefillLink[] {
  const out: PrefillLink[] = [];
  for (const r of results) {
    const l = r as Partial<PrefillLink> | undefined;
    if (l && typeof l.url === "string" && typeof l.button === "string" && l.url.startsWith("/") && !out.some((o) => o.url === l.url)) {
      out.push({ form: String(l.form), url: l.url, button: l.button });
    }
  }
  return out;
}
