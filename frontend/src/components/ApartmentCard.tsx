import type { Listing } from "@/lib/types";
import Sparkline from "./Sparkline";

const usd = (n: number) => "$" + n.toLocaleString();

export default function ApartmentCard({ listing, saved, onToggle, showSave }: {
  listing: Listing; saved: boolean; onToggle: () => void; showSave?: boolean;
}) {
  const first = listing.history[0];
  const diff = listing.rent - first;
  const pct = Math.abs((diff / first) * 100).toFixed(1);
  const dir = diff < 0 ? "↓" : diff > 0 ? "↑" : "–";
  return (
    <article className="card apt">
      <div className="apt-head">
        <div>
          <h3>{listing.address}</h3>
          <p className="muted">{listing.area.split(",")[0]} · {listing.beds === 0 ? "Studio" : `${listing.beds} bed`} · {listing.sqft} sq ft</p>
        </div>
        <button className="icon" aria-label="Open listing" title="Open listing">⛓</button>
      </div>
      <div className="apt-price">
        <strong>{usd(listing.rent)}</strong><span className="muted"> / mo</span>
        <span className="delta">{dir} {usd(Math.abs(diff))} ({pct}%)</span>
      </div>
      <Sparkline values={listing.history} />
      <div className="apt-axis muted"><span>{listing.historyStart}</span><span>{listing.historyEnd}</span></div>
      {showSave && (
        <button className={"save-btn" + (saved ? " on" : "")} onClick={onToggle}>
          {saved ? "Saved" : "+ Save apartment"}
        </button>
      )}
    </article>
  );
}
