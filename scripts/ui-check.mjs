#!/usr/bin/env node
// Browser check: load every page at 375px and 1280px in all four themes and fail on console errors, failed
// requests, horizontal scrolling at 375px, or a page without an <h1>. Screenshots go to docs/screens/ (gitignored).
//
//   (cd scripts && npm install && npx playwright install chromium)   # once; not part of any Docker image
//   node scripts/ui-check.mjs [BASE_URL]        # default http://localhost:3000 (the Mapbox token allows only
//                                               # that origin and rentorknot.us)
//   UI_THEMES=desert-clay UI_ONLY=/find,/zip node scripts/ui-check.mjs
//   UI_EXTRAS_ONLY=1 runs only the interaction checks; UI_EXTRAS=0 skips them (map pan, theme first paint, ...).
//   (UI_EXTRAS=0) skips the interaction checks (map pan, theme first paint, /saved multi-select, Find panel).
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
  const room = fbAll.find((l) => l.unit_type === "room");
  const fbZip = fbAll.find((l) => core.has(l.zip))?.zip || "92104";
  const pages = [
    ["home", "/"], ["about", "/about"], ["advisor", "/advisor"], ["alerts", "/alerts"], ["areas", "/areas"],
    ["buyer", "/buyer"], ["find", "/find"], ["find-facebook", "/find?source=facebook"], ["gouging", "/gouging"],
    ["owner", "/owner"], ["owner-reach", "/owner/reach"], ["renter", "/renter"], ["saved", "/saved"],
    ["scenarios", "/scenarios"], ["tools", "/tools"], ["zip", "/zip/92104"], ["zip-facebook", `/zip/${fbZip}`],
    ["privacy", "/privacy"], ["terms", "/terms"],
  ];
  if (site) pages.push(["apartment", `/apartments/${site.id}`]);
  if (fb) pages.push(["apartment-facebook", `/apartments/${fb.id}`]);
  if (room) pages.push(["apartment-facebook-room", `/apartments/${room.id}`]);
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

// ---------- interaction checks (page loads and clicks only; never submits a form or presses Remove) ----------
const GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];

function watch(page, problems) {
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 200)}`); });
  page.on("pageerror", (e) => problems.push(`page error: ${String(e.message || e).slice(0, 200)}`));
}

/** Pan the home map at 375px from San Diego toward Orange County; a county file other than San Diego must load. */
async function mapPan(browser) {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await ctx.newPage();
  const problems = [], geo = [];
  watch(page, problems);
  page.on("response", (r) => { if (/\/geo\/[a-z-]+\.geojson/.test(r.url()) && r.ok()) geo.push(r.url().split("/geo/")[1]); });
  try {
    await page.goto(BASE + "/", { waitUntil: "load", timeout: 45000 });
    const canvas = page.locator("canvas.mapboxgl-canvas, canvas.maplibregl-canvas").first();
    await canvas.waitFor({ timeout: 20000 });
    await canvas.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2500);
    const box = await canvas.boundingBox();
    const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
    for (let i = 0; i < 6 && !geo.some((f) => f.startsWith("orange")); i++) {   // drag down-right = view moves north-west
      await page.mouse.move(cx - 60, cy - 70);
      await page.mouse.down();
      await page.mouse.move(cx + 40, cy + 70, { steps: 12 });
      await page.mouse.up();
      await page.waitForTimeout(1800);
    }
    if (!geo.some((f) => f.startsWith("orange"))) problems.push(`Orange County shapes did not load after panning (loaded: ${geo.join(", ") || "none"})`);
    await page.screenshot({ path: join(OUT, "extra-375-map-pan.png") });
  } catch (e) { problems.push(`map pan failed: ${String(e.message || e).split("\n")[0].slice(0, 200)}`); }
  await ctx.close();
  return { theme: "-", width: 375, name: "map-pan", path: "/ (pan to Orange County)", problems, note: geo.join(", ") };
}

/** The theme is set before first paint (no flash): the theme and page background at DOMContentLoaded equal the
 *  settled ones. With no saved theme, prefers-color-scheme: dark gets Cocoa Night. */
async function firstPaint(browser, theme) {
  const dark = theme === "first-visit-dark";
  const expected = dark ? "cocoa-night" : theme;
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, colorScheme: dark ? "dark" : "light" });
  await ctx.addInitScript((t) => {
    try { if (t) localStorage.setItem("rok.theme", t); } catch {}
    document.addEventListener("DOMContentLoaded", () => {
      window.__first = { theme: document.documentElement.dataset.theme || "", bg: getComputedStyle(document.body).backgroundColor };
    });
  }, dark ? null : theme);
  const page = await ctx.newPage();
  const problems = [];
  watch(page, problems);
  try {
    await page.goto(BASE + "/about", { waitUntil: "load", timeout: 45000 });
    await page.waitForTimeout(1500);
    const m = await page.evaluate(() => ({ first: window.__first, theme: document.documentElement.dataset.theme,
      bg: getComputedStyle(document.body).backgroundColor }));
    if (!m.first) problems.push("no DOMContentLoaded snapshot");
    else {
      if (m.first.theme !== expected) problems.push(`first paint theme ${m.first.theme || "(none)"}, expected ${expected}`);
      if (m.first.bg !== m.bg) problems.push(`background changed after load: ${m.first.bg} -> ${m.bg} (flash)`);
    }
    if (m.theme !== expected) problems.push(`settled theme ${m.theme}, expected ${expected}`);
  } catch (e) { problems.push(`load failed: ${String(e.message || e).split("\n")[0].slice(0, 200)}`); }
  await ctx.close();
  return { theme: expected, width: 375, name: dark ? "first-visit-dark" : "first-paint", path: "/about", problems };
}

/** /saved: shift-click two cards and the action bar appears. Remove is never pressed. */
async function savedSelect(browser, width) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 900 } });
  const page = await ctx.newPage();
  const problems = [];
  watch(page, problems);
  try {
    await page.goto(BASE + "/saved", { waitUntil: "load", timeout: 45000 });
    const cards = page.locator("[data-testid=saved-card]");
    await cards.nth(1).waitFor({ timeout: 20000 });
    await cards.nth(0).click({ modifiers: ["Shift"], position: { x: 30, y: 120 } });
    await cards.nth(1).click({ modifiers: ["Shift"], position: { x: 30, y: 120 } });
    const bar = page.locator("[data-testid=saved-action-bar]");
    await bar.waitFor({ state: "visible", timeout: 5000 });
    const text = await bar.innerText();
    if (!/2 selected/.test(text)) problems.push(`action bar says "${text.replace(/\s+/g, " ").slice(0, 80)}", expected 2 selected`);
    if (!page.url().endsWith("/saved")) problems.push(`shift-click navigated to ${page.url()}`);
    await page.screenshot({ path: join(OUT, `extra-${width}-saved-selection.png`), fullPage: true });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    if (await bar.isVisible()) problems.push("Escape did not clear the selection");
  } catch (e) { problems.push(`saved selection failed: ${String(e.message || e).split("\n")[0].slice(0, 200)}`); }
  await ctx.close();
  return { theme: "desert-clay", width, name: "saved-select", path: "/saved (shift-click two)", problems };
}

/** /find with the "Not sure where to look?" panel opened, for a screenshot. Opening it makes the panel rank ZIPs with
 *  its default budget (Gemini summaries for that request are cached); this script fills and submits nothing. */
async function findPanel(browser, width) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 900 } });
  const page = await ctx.newPage();
  const problems = [];
  watch(page, problems);
  try {
    await page.goto(BASE + "/find", { waitUntil: "load", timeout: 45000 });
    await page.locator("[data-testid=starter-panel] summary").click();
    await page.getByRole("button", { name: /^Show listings in / }).first().waitFor({ timeout: 30000 });
    await page.screenshot({ path: join(OUT, `extra-${width}-find-starter.png`), fullPage: true });
  } catch (e) { problems.push(`find panel failed: ${String(e.message || e).split("\n")[0].slice(0, 200)}`); }
  await ctx.close();
  return { theme: "desert-clay", width, name: "find-starter", path: "/find (Starter panel open)", problems };
}

async function extras() {
  const out = [];
  let browser = await chromium.launch({ args: GL_ARGS });
  out.push(await mapPan(browser));
  await browser.close();
  browser = await chromium.launch();
  for (const t of [...THEMES, "first-visit-dark"]) out.push(await firstPaint(browser, t));
  for (const w of WIDTHS) out.push(await savedSelect(browser, w));
  for (const w of WIDTHS) out.push(await findPanel(browser, w));
  await browser.close();
  for (const r of out) process.stdout.write(r.problems.length ? "F" : ".");
  return out;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const pages = process.env.UI_EXTRAS_ONLY === "1" ? [] : await targets();
  const results = [];
  // A fresh browser every BATCH loads: a long-lived Chromium runs out of software WebGL contexts on map pages
  // ("Failed to initialize WebGL"), which is a property of headless SwiftShader, not of the site.
  const BATCH = Number(process.env.UI_BATCH || 12);
  const jobs = [];
  for (const theme of THEMES) for (const width of WIDTHS) for (const [name, path] of pages) jobs.push([theme, width, name, path]);
  for (let start = 0; start < jobs.length; start += BATCH) {
    // Software WebGL (SwiftShader) so the Mapbox map renders without a GPU.
    const browser = await chromium.launch({ args: GL_ARGS });
    const chunk = jobs.slice(start, start + BATCH);
    let next = 0;
    await Promise.all(Array.from({ length: PARALLEL }, async () => {
      while (next < chunk.length) {
        const j = chunk[next++];
        const r = await check(browser, ...j);
        results.push(r);
        process.stdout.write(r.problems.length ? "F" : ".");
      }
    }));
    await browser.close();
  }
  if (process.env.UI_EXTRAS !== "0" && !ONLY) results.push(...await extras());
  process.stdout.write("\n");
  const bad = results.filter((r) => r.problems.length).sort((a, b) => (a.name + a.theme + a.width).localeCompare(b.name + b.theme + b.width));
  for (const r of bad) console.log(`FAIL ${r.theme} ${r.width} ${r.path}\n  - ${r.problems.join("\n  - ")}`);
  writeFileSync(join(OUT, "results.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), results }, null, 2));
  console.log(`${results.length - bad.length}/${results.length} checks passed (${pages.length} pages x ${WIDTHS.length} widths x ${THEMES.length} themes, plus interaction checks) against ${BASE}`);
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
