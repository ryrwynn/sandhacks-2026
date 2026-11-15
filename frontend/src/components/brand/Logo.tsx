/* Placeholder brand mark. To use a real logo, replace frontend/public/brand/logo.svg (any square-ish SVG works). */
export default function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/brand/logo.svg" alt="" width={32} height={32} className="h-8 w-8 shrink-0" />
      <span className="text-lg font-bold tracking-tight text-ink">RentOrKnot</span>
    </span>
  );
}
