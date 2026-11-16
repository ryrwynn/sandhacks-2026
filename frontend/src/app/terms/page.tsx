import type { Metadata } from "next";
import { LegalDoc } from "@/components/LegalDoc";

export const metadata: Metadata = { title: "Terms · RentOrKnot" };

export default function TermsPage() {
  return (
    <LegalDoc
      title="Terms"
      intro="By using RentOrKnot you agree to these terms."
      sections={[
        { h: "Information only", body: <p>RentOrKnot is informational. It is not legal, financial or real-estate advice. Talk to a qualified professional before you act on a result.</p> },
        { h: "Estimates can be wrong", body: <p>Estimates, forecasts and rent-check results can be wrong. They are based on public data and the numbers you enter.</p> },
        { h: "Listings come from third parties", body: <p>Listings come from third parties and may be out of date or no longer available. Check with the source before you rely on one.</p> },
        { h: "We never contact anyone for you", body: <p>RentOrKnot never contacts landlords and never posts anything anywhere on your behalf.</p> },
        { h: "Acceptable use", body: (<ul className="list-disc space-y-1 pl-5">
          <li>No scraping or automated bulk access.</li>
          <li>No abusing the forms.</li>
          <li>No attempts to break or overload the site.</li>
        </ul>) },
        { h: "No warranty, limited liability", body: <p>The site is provided &ldquo;as is&rdquo; without warranty of any kind. To the extent the law allows, we are not liable for losses from using it.</p> },
        { h: "Governing law", body: <p>California law governs these terms.</p> },
        { h: "Changes", body: <p>We may change these terms. When we do, we update the date at the top of this page.</p> },
      ]}
    />
  );
}
