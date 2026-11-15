import { Building, Building2, BedDouble, House, Hotel, type LucideIcon } from "lucide-react";

/** Townhouse: two joined homes (lucide has no row-house icon). */
function Townhouse({ size = 20, className, ...rest }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} {...rest}>
      <path d="M2 21V11l5-4 5 4v10" /><path d="M12 21V11l5-4 5 4v10" /><path d="M2 21h20" /><path d="M5 21v-4h4v4M15 21v-4h4v4" />
    </svg>
  );
}

const ICONS: Record<string, LucideIcon | typeof Townhouse> = {
  apartment: Building2, condo: Hotel, house: House, townhouse: Townhouse, room: BedDouble,
  single_family: House, multi_family: Building, duplex: Townhouse,
};

/** Pictogram for a property type; unknown types fall back to a building. */
export default function PropertyIcon({ type, size = 18, className = "" }: { type: string | null | undefined; size?: number; className?: string }) {
  const I = (type && ICONS[type.toLowerCase().replace(/[ -]/g, "_")]) || Building;
  return <I size={size} aria-hidden="true" className={`shrink-0 ${className}`} />;
}
