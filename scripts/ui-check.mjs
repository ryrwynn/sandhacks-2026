#!/usr/bin/env node
// Browser check: load every page at 375px and 1280px in all four themes and fail on console errors, failed
// requests, horizontal scrolling at 375px, or a page without an <h1>. Screenshots go to docs/screens/ (gitignored).
//
//   (cd scripts && npm install && npx playwright install chromium)   # once; not part of any Docker image
//   node scripts/ui-check.mjs [BASE_URL]        # default http://localhost:3000 (the Mapbox token allows only
//                                               # that origin and rentorknot.us)
//   UI_THEMES=desert-clay UI_ONLY=/find,/zip node scripts/ui-check.mjs
//
// Only loads pages: it never fills or submits a form, so nothing calls Gemini (letter, advisor) or posts anywhere.
// /renter/letter/[id] is skipped because opening it asks Gemini for a letter.
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = createRequire(join(here, "package.json"))("playwright");
const BASE = (process.argv[2] || process.env.UI_BASE_URL || "http://localhost:3000").replace(/\/$/, "");
const OUT = join(here, "..", "docs", "screens");
const THEMES = (process.env.UI_THEMES || "desert-clay,sage-linen,cocoa-night,harbor-dusk").split(",");
const WIDTHS = [375, 1280];
const ONLY = process.env.UI_ONLY ? process.env.UI_ONLY.split(",") : null;
const PARALLEL = Number(process.env.UI_PARALLEL || 4);
const SETTLE_MS = Number(process.env.UI_SETTLE_MS || 2500);

async function api(path) {
  const r = await fetch(`${BASE}/api${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

async function targets() {
  const site = (await api("/listings?source=listing_sites&limit=1")).items[0];
  const fbAll = (await api("/listings?source=facebook&limit=100")).items;
  const core = new Set((await api("/zips")).zips.map((z) => z.zip));
  const fb = fbAll.find((l) => l.unit_type === "entire_unit") || fbAll[0];
  const fbZip = fbAll.find((l) => core.has(l.zip))?.zip || "92104";
  const pages = [
    ["home", "/"], ["about", "/about"], ["advisor", "/advisor"], ["alerts", "/alerts"], ["areas", "/areas"],
    ["buyer", "/buyer"], ["find", "/find"], ["find-facebook", "/find?source=facebook"], ["gouging", "/gouging"],
    ["owner", "/owner"], ["owner-reach", "/owner/reach"], ["renter", "/renter"], ["saved", "/saved"],
    ["scenarios", "/scenarios"], ["tools", "/tools"], ["zip", "/zip/92104"], ["zip-facebook", `/zip/${fbZip}`],
  ];
  if (site) pages.push(["apartment", `/apartments/${site.id}`]);
  if (fb) pages.push(["apartment-facebook", `/apartments/${fb.id}`]);
  return pages.filter(([name, path]) => !ONLY || ONLY.some((o) => path === o || name === o.replace(/^\//, "")));
}

const IGNORE_REQUEST = [/net::ERR_ABORTED/, /events\.mapbox\.com/];   // aborted on navigation; Mapbox telemetry

async function check(browser, theme, width, name, path) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 900 }, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("rok.theme", t); } catch {} }, theme);
  const page = await ctx.newPage();
  const problems = [];
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 200)}`); });
  page.on("pageerror", (e) => problems.push(`page error: ${String(e.message || e).slice(0, 200)}`));
  page.on("requestfailed", (r) => {
    const why = `${r.failure()?.errorText || ""} ${r.url()}`;
    if (!IGNORE_REQUEST.some((re) => re.test(why))) problems.push(`request failed: ${why.slice(0, 200)}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !IGNORE_REQUEST.some((re) => re.test(r.url()))) problems.push(`HTTP ${r.status()}: ${r.url().slice(0, 160)}`);
  });
  try {
    await page.goto(BASE + path, { waitUntil: "load", timeout: 45000 });
    await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(SETTLE_MS);
    const m = await page.evaluate(() => ({
      h1: document.querySelectorAll("h1").length,
      scroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      theme: document.documentElement.dataset.theme || "",
    }));
    if (m.h1 === 0) problems.push("no <h1>");
    if (width === 375 && m.scroll > 1) problems.push(`horizontal scroll: ${m.scroll}px wider than the viewport`);
    if (m.theme && m.theme !== theme) problems.push(`theme is ${m.theme}, expected ${theme}`);
    await page.screenshot({ path: join(OUT, `${theme}-${width}-${name}.png`), fullPage: true });
  } catch (e) {
    problems.push(`load failed: ${String(e.message || e).split("\n")[0].slice(0, 200)}`);
  }
  await ctx.close();
  return { theme, width, name, path, problems: [...new Set(problems)] };
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const pages = await targets();
  const results = [];
  // One browser per theme: a long-lived Chromium runs out of software WebGL contexts after ~40 map pages.
  for (const theme of THEMES) {
    // Software WebGL (SwiftShader) so the Mapbox map renders without a GPU.
    const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
    const jobs = [];
    for (const width of WIDTHS) for (const [name, path] of pages) jobs.push([theme, width, name, path]);
    let next = 0;
    await Promise.all(Array.from({ length: PARALLEL }, async () => {
      while (next < jobs.length) {
        const j = jobs[next++];
        const r = await check(browser, ...j);
        results.push(r);
        process.stdout.write(r.problems.length ? "F" : ".");
      }
    }));
    await browser.close();
  }
  process.stdout.write("\n");
  const bad = results.filter((r) => r.problems.length).sort((a, b) => (a.name + a.theme + a.width).localeCompare(b.name + b.theme + b.width));
  for (const r of bad) console.log(`FAIL ${r.theme} ${r.width} ${r.path}\n  - ${r.problems.join("\n  - ")}`);
  writeFileSync(join(OUT, "results.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), results }, null, 2));
  console.log(`${results.length - bad.length}/${results.length} page loads passed (${pages.length} pages x ${WIDTHS.length} widths x ${THEMES.length} themes) against ${BASE}`);
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
