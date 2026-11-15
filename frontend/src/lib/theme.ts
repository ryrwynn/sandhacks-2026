export const THEME_KEY = "rok.theme";
export type ThemeId = "desert-clay" | "sage-linen" | "cocoa-night" | "harbor-dusk";
export const THEMES: { id: ThemeId; name: string; dark: boolean; swatch: [string, string, string]; font: string }[] = [
  { id: "desert-clay", name: "Desert Clay", dark: false, swatch: ["#ffe8d6", "#cb997e", "#646953"], font: "Geist" },
  { id: "sage-linen", name: "Sage Linen", dark: false, swatch: ["#eceee0", "#b88a5c", "#46633f"], font: "Nunito" },
  { id: "cocoa-night", name: "Cocoa Night", dark: true, swatch: ["#1f1a17", "#e8b48f", "#b2b998"], font: "DM Sans" },
  { id: "harbor-dusk", name: "Harbor Dusk", dark: true, swatch: ["#131b25", "#efc08c", "#8fb6dc"], font: "Atkinson Hyperlegible" },
];
/** Runs in <head> before paint: the saved theme, else the OS preference on the first visit. */
export const THEME_INIT_SCRIPT = `(function(){try{var t=null;try{t=localStorage.getItem("${THEME_KEY}")}catch(e){}var ok={"desert-clay":1,"sage-linen":1,"cocoa-night":1,"harbor-dusk":1};if(!t||!ok[t]){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches?"cocoa-night":"desert-clay"}document.documentElement.setAttribute("data-theme",t)}catch(e){}})();`;
