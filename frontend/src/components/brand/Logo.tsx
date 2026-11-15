/* Brand mark. The shape comes from public/brand/logo.svg and is drawn as a CSS mask filled with the
   theme's ink color, so it reads in every theme (light and dark). To change the logo, replace that file;
   keep the width below at 32 × (viewBox width ÷ viewBox height). */
const MASK = "url(/brand/logo.svg) center / contain no-repeat";

export default function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span aria-hidden="true" className="block h-8 w-[43px] shrink-0 bg-ink" style={{ mask: MASK, WebkitMask: MASK }} />
      <span className="text-lg font-bold tracking-tight text-ink">RentOrKnot</span>
    </span>
  );
}
