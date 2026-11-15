#!/usr/bin/env node
// Contrast check for every theme in frontend/src/app/globals.css.
// Text pairs need 4.5:1; UI and chart-line pairs need 3:1. Exits 1 on any failure.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../frontend/src/app/globals.css"), "utf8");
const themes = {};
for (const m of css.matchAll(/\[data-theme="([a-z-]+)"\]\s*\{([^}]*)\}/g)) {
  const vars = {};
  for (const v of m[2].matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) vars[v[1]] = v[2];
  themes[m[1]] = vars;
}

const lum = (hex) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const TEXT = [
  ["ink", "bg"], ["ink", "surface"], ["ink", "tint"], ["ink", "line"],
  ["muted", "bg"], ["muted", "surface"], ["muted", "tint"],
  ["text2", "surface"], ["text2", "bg"], ["faint", "surface"],
  ["on-primary", "primary"], ["on-primary", "primary-hover"], ["on-primary", "accent-strong"], ["on-ink", "ink"],
  ["primary", "bg"], ["primary", "surface"], ["accent-strong", "bg"], ["accent-strong", "surface"],
  ["good", "surface"], ["good", "ok-bg"], ["good", "ok-bg2"],
  ["warn", "surface"], ["warn", "bg"], ["warn", "warn-bg"],
  ["caution-text", "caution-bg"], ["caution-text", "caution-bg2"],
];
const UI = [["primary", "surface"], ["primary", "bg"], ["accent-strong", "surface"], ["accent-strong", "bg"], ["caution-mark", "surface"]];

if (Object.keys(themes).length < 3) { console.log("FAIL: expected at least 3 themes, found " + Object.keys(themes).length); process.exit(1); }
let fail = 0;
for (const [name, t] of Object.entries(themes)) {
  const bad = [];
  for (const [list, min] of [[TEXT, 4.5], [UI, 3]]) {
    for (const [fg, bg] of list) {
      if (!t[fg] || !t[bg]) { bad.push(`${fg}/${bg} missing`); continue; }
      const r = ratio(t[fg], t[bg]);
      if (r < min) bad.push(`${fg} on ${bg} ${r.toFixed(2)} < ${min}`);
    }
  }
  console.log(`${bad.length ? "FAIL" : "ok  "} ${name}${bad.length ? "\n  " + bad.join("\n  ") : ""}`);
  fail += bad.length;
}
process.exit(fail ? 1 : 0);
