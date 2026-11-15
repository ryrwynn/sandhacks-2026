// Control scale: height from --ctl / --ctl-sm (rem, globals.css), font from the control, padding in em so it follows the font.
export const inputCls =
  "w-full min-h-[var(--ctl)] rounded-lg border border-line bg-surface px-[0.75em] py-[0.5em] text-base text-ink placeholder:text-slate-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30";
export const btnCls =
  "inline-flex min-h-[var(--ctl)] items-center justify-center rounded-lg bg-primary px-[1em] py-[0.5em] text-base font-semibold text-on-primary hover:bg-primary-hover disabled:opacity-50";
export const btnGhostCls =
  "inline-flex min-h-[var(--ctl)] items-center justify-center rounded-lg border border-line bg-surface px-[1em] py-[0.5em] text-base font-medium text-ink hover:bg-slate-100";
export const selectCls =
  "min-h-[var(--ctl)] max-w-full rounded-lg border border-line bg-surface px-[0.75em] py-[0.5em] text-base text-ink focus:outline-none focus:ring-2 focus:ring-primary/30";
export const cardCls = "rounded-xl bg-surface shadow-[0_1px_3px_rgba(46,49,39,0.12),0_4px_14px_rgba(46,49,39,0.05)]";
