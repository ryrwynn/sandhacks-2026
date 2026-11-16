import type { Metadata } from "next";
import { LegalDoc } from "@/components/LegalDoc";

export const metadata: Metadata = { title: "Privacy · RentOrKnot" };

export default function PrivacyPage() {
  return (
    <LegalDoc
      title="Privacy"
      intro="RentOrKnot reads public rental and home-price data and explains it. This page says what is stored, where, and how to have it removed."
      sections={[
        { h: "Your saved apartments", body: <p>Saves live in this browser (its local storage). Nothing is sent to us unless you choose to sign in.</p> },
        { h: "Optional Google sign-in", body: (<>
          <p>Signing in is optional and lets your saves follow you across devices. We store a hash of your Google account ID (SHA-256 with a secret kept on our server), plus the IDs of the listings you saved and the prices and targets you saved with them.</p>
          <p>We do not store your email address or name.</p>
        </>) },
        { h: "Deleting your data", body: (<ul className="list-disc space-y-1 pl-5">
          <li>Remove your saves in the app and sign out.</li>
          <li>Clear this site&apos;s data in your browser to remove the local copy.</li>
          <li>A way to ask for the server copy to be deleted is coming.</li>
        </ul>) },
        { h: "Rent Cap checks", body: <>When you run a Rent Cap check, the server stores what you entered (the address, rents, dates and year built) with the result, so the reply letter can be made from it. It is not linked to you or your account. A way to ask for a check to be deleted is coming.</> },
        { h: "Ads and tracking", body: <p>There are no ads, no tracking or analytics scripts, and we do not sell data.</p> },
        { h: "Data from public sources", body: (<>
          <p>We collect public data: Zillow listings (through a data provider), Zillow Research indexes, Census data, OpenStreetMap, and public Facebook groups.</p>
          <p>For Facebook-derived listings we keep only extracted fields (price, bedrooms, unit type, ZIP or neighborhood, amenities and dates) and a link to the post. Post text, names, profile links and photos are not stored.</p>
          <p>A way to report a listing is coming. Until then, this site does not receive reports or removal requests.</p>
        </>) },
        { h: "Google Gemini", body: <p>We use Google Gemini to read and write text. It receives redacted post text and text you type into forms (for example the rent-check letter, the advisor and plain-language search), and is subject to Google&apos;s terms. Don&apos;t type anything you want kept private.</p> },
        { h: "Server logs", body: <p>The hosting server keeps standard request logs, such as IP address and user agent, for operating and securing the site.</p> },
              ]}
    />
  );
}
