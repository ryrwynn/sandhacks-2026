#!/usr/bin/env node
// End-to-end use of every feature against a running site (default http://localhost:3000), like a person would:
// filters, saving, selection, alerts, every tool form. Screenshots go to docs/screens/e2e-*.png (gitignored).
//
//   node scripts/e2e.mjs [BASE_URL]          E2E_ONLY=find,saved node scripts/e2e.mjs
//
// Safety: rent checks and gouging checks are sent with is_demo=true (the request is rewritten); the area request
// asks for an area that is already covered, so nothing is queued for a paid scrape; nothing is posted anywhere else.
// AI features (letter, listing analysis, advisor, needs matching) are used once each.
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = createRequire(join(here, "package.json"))("playwright");
const BASE = (process.argv[2] || process.env.E2E_BASE_URL || "http://localhost:3000").replace(/\/$/, "");
const OUT = join(here, "..", "docs", "screens");
const ONLY = process.env.E2E_ONLY ? process.env.E2E_ONLY.split(",") : null;
const IGNORE = [/net::ERR_ABORTED/, /events\.mapbox\.com/, /api\.mapbox\.com\/.*\.pbf/];

const results = [];
let page, ctx, problems = [];

function expect(cond, msg) { if (!cond) throw new Error(msg); }
const money = (s) => Number(String(s).replace(/[^0-9.]/g, ""));

async function step(name, fn) {
  if (ONLY && !ONLY.some((o) => name.startsWith(o))) return;
  problems = [];
  const t0 = Date.now();
  let error = null;
  try { await fn(); } catch (e) { error = String(e.message || e).split("\n")[0].slice(0, 300); }
  await page.waitForTimeout(300);
  const issues = [...(error ? [error] : []), ...new Set(problems)];
  try { await page.screenshot({ path: join(OUT, `e2e-${name}.png`), fullPage: true }); } catch {}
  results.push({ name, ok: issues.length === 0, issues, ms: Date.now() - t0 });
  process.stdout.write(`${issues.length ? "FAIL" : "ok  "} ${name}${issues.length ? "\n      - " + issues.join("\n      - ") : ""}\n`);
}

async function go(path) {
  await page.goto(BASE + path, { waitUntil: "load", timeout: 45000 });
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
}
const text = async (sel) => (await page.locator(sel).first().innerText()).replace(/\s+/g, " ").trim();
const body = () => page.locator("body").innerText();
/** Fill a labelled field whether it is an input or a select. */
async function setField(label, value, nth = 0) {
  const el = page.getByLabel(label).nth(nth);
  const tag = await el.evaluate((e) => e.tagName);
  if (tag === "SELECT") await el.selectOption(value); else await el.fill(value);
}
async function noSample() { expect(!(await body()).includes("Showing sample data"), "sample-data banner shown"); }
async function navBadge() {
  const t = await page.locator("header").first().innerText();
  const m = t.match(/Saved apartments\s*(\d+)/);
  return m ? Number(m[1]) : 0;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  // Rent and gouging checks are stored: mark the ones this script makes as demo rows.
  await ctx.route(/\/api\/checks(\/gouging)?$/, async (route) => {
    const r = route.request();
    if (r.method() !== "POST") return route.continue();
    const b = JSON.parse(r.postData() || "{}");
    return route.continue({ postData: JSON.stringify({ ...b, is_demo: true }) });
  });
  page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 180)}`); });
  page.on("pageerror", (e) => problems.push(`page error: ${String(e.message || e).slice(0, 180)}`));
  page.on("response", (r) => {
    if (r.status() >= 400 && !IGNORE.some((re) => re.test(r.url()))) problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(BASE, "").slice(0, 120)}`);
  });
  page.on("requestfailed", (r) => {
    const why = `${r.failure()?.errorText} ${r.url()}`;
    if (!IGNORE.some((re) => re.test(why))) problems.push(`request failed: ${why.slice(0, 160)}`);
  });

  // ---------------- Market overview ----------------
  await step("home-load", async () => {
    await go("/");
    await noSample();
    const v = money(await text("#market-h + p"));
    expect(v > 1000 && v < 10000, `market headline ${v} not a rent`);
    expect(await page.locator(".recharts-line").count() >= 1, "no chart line");
    expect((await body()).includes("Updated weekly"), "no 'Updated weekly'");
  });
  await step("home-filters", async () => {
    await go("/");
    const area = page.getByRole("combobox", { name: "Area" }).first();
    const beds = page.getByRole("combobox", { name: "Bedrooms" }).first();
    await area.selectOption("92104");
    await page.waitForTimeout(2500);
    const a = money(await text("#market-h + p"));
    await beds.selectOption("2");
    await page.waitForTimeout(2500);
    const label = await text("#market-h");
    const b = money(await text("#market-h + p"));
    expect(/Median asking rent, 2 bed|Typical rent/.test(label), `label "${label}"`);
    expect(b > 1000, `2-bed headline ${b}`);
    // Months on the x axis must be in order.
    const ticks = await page.locator(".recharts-xAxis .recharts-cartesian-axis-tick-value").allInnerTexts();
    const ts = ticks.map((t) => Date.parse("1 " + t)).filter((x) => !Number.isNaN(x));
    expect(ts.every((t, i) => i === 0 || t > ts[i - 1]), `x-axis months out of order: ${ticks.join(", ")}`);
    for (const r of ["1M", "3M", "6M", "All", "1Y"]) {
      await page.getByRole("button", { name: r, exact: true }).click();
      await page.waitForTimeout(900);
    }
    await page.getByRole("combobox", { name: "Property type" }).first().selectOption("condo");
    await page.waitForTimeout(1500);
    const cb = page.getByRole("checkbox", { name: /Listing sites only/ });
    if (await cb.count()) { await cb.check(); await page.waitForTimeout(1500); await cb.uncheck(); }
    expect(a > 1000, `92104 headline ${a}`);
  });

  // ---------------- Find ----------------
  await step("find-filters", async () => {
    await go("/find");
    await noSample();
    await page.locator("[data-testid=save-toggle]").first().waitFor({ timeout: 15000 });
    const head = await text("main h2");
    expect(/\d/.test(head) && /in San Diego/.test(head), `results heading "${head}"`);
    await page.getByRole("combobox", { name: "Source" }).selectOption("facebook");
    await page.waitForTimeout(2500);
    const cards = page.locator("article");
    const n = await cards.count();
    expect(n > 0, "no Facebook cards");
    for (let i = 0; i < Math.min(n, 8); i++) expect((await cards.nth(i).innerText()).includes("Facebook group"), `card ${i} not Facebook`);
    await page.getByRole("combobox", { name: "Whole unit or room" }).selectOption("room");
    await page.waitForTimeout(2500);
    const rooms = await cards.count();
    expect(rooms > 0, "no rooms");
    for (let i = 0; i < Math.min(rooms, 8); i++) expect((await cards.nth(i).innerText()).includes("Roommate wanted"), `room card ${i} lacks Roommate wanted`);
    await page.getByRole("combobox", { name: "Whole unit or room" }).selectOption("any");
    await page.getByRole("combobox", { name: "Source" }).selectOption("all");
    await page.getByRole("combobox", { name: "Sort" }).selectOption("price_asc");
    await page.waitForTimeout(2500);
    const prices = (await page.locator("article strong").allInnerTexts()).map(money).slice(0, 12);
    expect(prices.every((p, i) => i === 0 || p >= prices[i - 1]), `not ascending: ${prices.join(",")}`);
    const before = await cards.count();
    const first = await page.locator("article h3").first().innerText();
    await page.getByRole("button", { name: "Next" }).click();
    await page.waitForTimeout(3000);
    expect((await page.locator("article h3").first().innerText()) !== first, "Next page showed the same first card");
    expect((await page.locator("[data-testid=find-showing]").innerText()).startsWith("Showing 16"), "page 2 does not say Showing 16");
  });
  await step("find-save", async () => {
    await go("/find");
    await page.locator("[data-testid=save-toggle]").first().waitFor({ timeout: 15000 });
    const b0 = await navBadge();
    const btn = page.locator("[data-testid=save-toggle][aria-pressed=false]").first();
    await btn.click();
    await page.waitForTimeout(500);
    expect((await navBadge()) === b0 + 1, `badge ${b0} -> ${await navBadge()}`);
    // Save buttons line up in a row
    const ys = await page.locator("[data-testid=save-toggle]").evaluateAll((els) => els.slice(0, 3).map((e) => Math.round(e.getBoundingClientRect().bottom)));
    expect(new Set(ys).size === 1, `Save buttons not aligned: ${ys}`);
  });
  await step("find-starter", async () => {
    await go("/find");
    await page.locator("[data-testid=starter-panel] summary").click();
    const pick = page.getByRole("button", { name: /^Show listings in / }).first();
    await pick.waitFor({ timeout: 30000 });
    const name = (await pick.innerText()).replace("Show listings in ", "").trim();
    await pick.click();
    await page.waitForTimeout(3000);
    const head = await text("main h2");
    expect(head.includes(name), `heading "${head}" doesn't name ${name}`);
    const area = await page.getByRole("combobox", { name: "Area" }).inputValue();
    expect(/^\d{5}$/.test(area), `area filter not set (${area})`);
  });
  await step("find-area-search", async () => {
    await go("/find");
    await page.getByText("Looking somewhere else?").click();
    const box = page.getByRole("searchbox").or(page.getByPlaceholder(/ZIP or city/)).first();
    await box.fill("La Jolla");
    await box.press("Enter");
    await page.waitForTimeout(2500);
    expect((await body()).includes("92037"), "La Jolla (92037) not found");
  });

  // ---------------- Apartment pages ----------------
  let siteId, fbId, roomId;
  await step("apartment", async () => {
    // The rent-check link carries the address when the listing has one (many county listings have none): look for one in
    // the first 300, else take the first listing and check the ZIP instead.
    let pick, first;
    for (let off = 0; off < 300 && !pick; off += 100) {
      const j = await (await fetch(`${BASE}/api/listings?source=listing_sites&limit=100&offset=${off}`)).json();
      if (!j.items?.length) break;
      first ??= j.items[0];
      pick = j.items.find((l) => l.address && l.n_observations > 1) ?? j.items.find((l) => l.address);
    }
    pick ??= first;
    siteId = pick.id;
    await go(`/apartments/${siteId}`);
    await noSample();
    await page.locator("h1").first().waitFor();
    const t = await body();
    expect(/Asking price history/i.test(t), "no price history");
    expect(/What it should rent for/i.test(t), "no fair-rent section");
    const save = page.getByRole("button", { name: /Save apartment|Saved/ }).first();
    if (await save.count()) { await save.click(); await page.waitForTimeout(400); }
    const link = page.locator("main a[href^='/renter?']").first();
    expect(await link.count(), "no rent-check link");
    await link.click();
    await page.waitForURL(/\/renter/);
    await page.waitForTimeout(1500);
    if (pick.address) {
      const addr = await page.getByLabel("Your address").inputValue();
      expect(addr.length > 3, "rent check not prefilled with the address");
    }
    expect((await page.getByLabel("ZIP code").inputValue()) === pick.zip, "rent check not prefilled with the ZIP");
  });
  await step("apartment-facebook", async () => {
    const j = await (await fetch(`${BASE}/api/listings?source=facebook&limit=50`)).json();
    fbId = j.items.find((l) => l.unit_type === "entire_unit")?.id ?? j.items[0].id;
    roomId = j.items.find((l) => l.unit_type === "room")?.id;
    await go(`/apartments/${fbId}`);
    await noSample();
    const t = await body();
    expect(t.includes("View post on Facebook") || t.includes("Facebook"), "no Facebook link/badge");
    expect(!/Address not listed/.test(await text("h1")), "Facebook title shows 'Address not listed'");
    if (roomId) {
      await go(`/apartments/${roomId}`);
      expect((await body()).includes("Rooms and sublets aren't compared"), "room page lacks the no-estimate note");
    }
  });

  // ---------------- Saved + alerts ----------------
  await step("saved-select", async () => {
    await go("/saved");
    const cards = page.locator("[data-testid=saved-card]");
    await cards.nth(1).waitFor({ timeout: 20000 });
    const n0 = await cards.count();
    await cards.nth(0).click({ modifiers: ["Shift"], position: { x: 30, y: 120 } });
    await cards.nth(1).click({ modifiers: ["Shift"], position: { x: 30, y: 120 } });
    const bar = page.locator("[data-testid=saved-action-bar]");
    await bar.waitFor({ state: "visible" });
    expect((await bar.innerText()).includes("2 selected"), "bar doesn't say 2 selected");
    // Open in new tabs: a popup opens (or the blocked-links list shows)
    const pop = ctx.waitForEvent("page", { timeout: 4000 }).catch(() => null);
    await bar.getByRole("button", { name: /Open sources/ }).click();
    const p2 = await pop;
    const blocked = await page.locator("[data-testid=saved-blocked-links]").count();
    expect(p2 || blocked, "nothing opened and no blocked-links list");
    if (p2) await p2.close();
    await bar.getByRole("button", { name: /Remove from saved/ }).click();
    await page.waitForTimeout(500);
    expect((await cards.count()) === n0 - 2, `remove: ${n0} -> ${await cards.count()}`);
    await page.locator("[data-testid=saved-undo-toast]").getByRole("button", { name: "Undo" }).click();
    await page.waitForTimeout(500);
    expect((await cards.count()) === n0, `undo: ${await cards.count()} != ${n0}`);
    await page.getByRole("button", { name: "Select", exact: true }).click();
    await page.locator("input[type=checkbox][aria-label^='Select ']").first().check();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    expect(!(await bar.isVisible()), "Escape didn't clear");
    await page.getByRole("combobox", { name: "Sort saved apartments" }).selectOption("price");
    const prices = (await cards.locator("strong").allInnerTexts()).map(money);
    expect(prices.every((p, i) => i === 0 || p >= prices[i - 1]), `saved sort not ascending: ${prices}`);
  });
  await step("alerts", async () => {
    await go("/alerts");
    const box = page.getByLabel("Alert me at or below ($ / month)").first();
    await box.waitFor({ timeout: 15000 });
    await box.fill("99999");
    await page.getByRole("button", { name: "Set target" }).first().click();
    await page.waitForTimeout(600);
    const t = await body();
    expect(/Below your target/.test(t), "target above price didn't create an alert");
    expect((await navBadge()) >= 0, "");
    await page.getByRole("button", { name: "Got it" }).first().click().catch(() => {});
    await page.getByRole("button", { name: "Clear" }).first().click().catch(() => {});
  });

  // ---------------- Renter tools ----------------
  let checkHref = null;
  await step("renter-check", async () => {
    await go("/renter");
    expect(!(await body()).includes("Find a place"), "'Find a place' tab still there");
    await page.getByLabel("Your address").fill("2519 El Cajon Blvd, San Diego, CA 92104");
    await page.getByLabel("Year built").fill("1985");
    await page.getByLabel("Lowest rent, past 12 months ($)").fill("2400");
    await page.getByLabel("New rent ($)").fill("2700");
    await page.getByLabel("Takes effect on").fill("2026-12-01");
    await page.getByRole("button", { name: "Check my increase" }).click();
    await page.getByText(/Over the cap|Within the cap|Not covered|Can't tell yet/).first().waitFor({ timeout: 20000 });
    const link = page.getByRole("link", { name: "Get a reply letter" });
    if (await link.count()) checkHref = await link.getAttribute("href");
  });
  await step("renter-letter", async () => {
    expect(checkHref, "no letter link from the check");
    await go(checkHref);
    await page.waitForFunction(() => document.body.innerText.length > 600, null, { timeout: 60000 });
    expect(/Dear|landlord/i.test(await body()), "letter text missing");
  });
  await step("renter-listing", async () => {
    await go("/renter");
    await page.getByRole("tab", { name: "Check a listing" }).click();
    await setField("ZIP code", "92104");
    await setField("Bedrooms", "1");
    await setField("Asking rent ($/month)", "2300");
    await page.getByRole("button", { name: "Check this price" }).click();
    await page.getByText(/typical range|expected|Expected/).first().waitFor({ timeout: 20000 });
  });

  // ---------------- Other tools ----------------
  await step("buyer", async () => {
    await go("/buyer");
    await noSample();
    await page.getByText(/of 100/).first().waitFor({ timeout: 30000 });
    const t = await body();
    expect(!/\d\.\d{3,}/.test(t), "a number with more than 2 decimals on /buyer");
    await page.getByLabel("Home price budget ($)").fill("700000");
    await page.getByRole("button", { name: /Find wealth-building ZIPs/ }).click();
    await page.waitForTimeout(4000);
    expect(/of 100/.test(await body()), "no ranking after budget change");
  });
  await step("owner", async () => {
    await go("/owner");
    await setField("ZIP code", "92104");
    await setField("Bedrooms", "1");
    await setField("Target rent ($/month)", "2400");
    await page.getByRole("button", { name: "See price position" }).click();
    await page.getByText(/percentile|Percentile/).first().waitFor({ timeout: 20000 });
    const text = page.getByLabel("Paste your listing text");
    if (await text.count()) {
      await text.fill("Sunny 1 bedroom in North Park with in-unit washer and dryer, parking, pets welcome. Walk to cafes on 30th St.");
      await page.getByRole("button", { name: "Analyze my listing" }).click();
      await page.getByText("Readability", { exact: true }).first().waitFor({ timeout: 45000 });
      expect(!(await body()).includes("Analyzing..."), "listing analysis still running");
    }
  });
  await step("owner-reach", async () => {
    await go("/owner/reach");
    await setField("ZIP", "92104");
    await setField("Bedrooms", "1");
    await setField("Rent you plan to ask ($)", "2400");
    await page.getByRole("button", { name: "Estimate reach" }).click();
    await page.getByText(/shortlist/).first().waitFor({ timeout: 45000 });
  });
  await step("gouging", async () => {
    await go("/gouging");
    await setField("ZIP code", "92104");
    await page.getByLabel("New rent charged or offered ($)").fill("2600");
    await page.getByLabel("Date it was charged or offered").fill("2026-10-20");
    await page.getByLabel("Rent before the emergency ($)").fill("2200");
    await page.getByRole("button", { name: "Check for price gouging" }).click();
    await page.getByText(/likely|within|limit|unclear|Unclear|not covered/i).nth(1).waitFor({ timeout: 20000 });
  });
  await step("scenarios", async () => {
    await go("/scenarios");
    await noSample();
    await page.waitForTimeout(3000);
    const zip = page.getByLabel("ZIP").first();
    if (await zip.count()) { await zip.selectOption({ index: 2 }).catch(async () => { await zip.fill("92104"); }); }
    const m = page.getByLabel("Measure").first();
    if (await m.count()) await m.selectOption({ index: 1 });
    await page.waitForTimeout(2500);
    expect(await page.locator(".recharts-surface").count() > 0, "no scenario chart");
  });
  await step("advisor", async () => {
    await go("/advisor");
    const needs = page.getByLabel("Describe what you need");
    if (await needs.count()) {
      await needs.fill("Quiet 1 bedroom under $2,500 near transit with laundry, pets OK");
      await page.getByRole("button", { name: "Find matches" }).click();
      await page.waitForTimeout(500);
      await page.waitForFunction(() => !document.body.innerText.includes("Matching..."), null, { timeout: 60000 });
    }
    const q = page.getByLabel("Your question");
    await q.fill("Is a 6% rent increase in 92104 allowed this year?");
    await page.getByRole("button", { name: /Send/ }).click();
    await page.waitForFunction(() => /Advisor:/.test(document.body.innerText), null, { timeout: 90000 });
  });
  await step("areas", async () => {
    await go("/areas");
    await noSample();
    await page.waitForTimeout(2000);
    const tier = page.getByLabel("Coverage level");
    await tier.selectOption("county");
    await page.waitForTimeout(2000);
    expect((await body()).includes("La Jolla") || (await body()).includes("92037"), "county tier doesn't list La Jolla");
    const add = page.getByPlaceholder(/ZIP|city/i).last();
    await add.fill("92104");
    await page.getByRole("button", { name: /Add|Request|Check/ }).last().click();
    await page.waitForTimeout(3000);
    expect(/already|covered/i.test(await body()), "already-covered area not reported as covered");
  });
  await step("zip-pages", async () => {
    await go("/zip/92104");
    await noSample();
    expect((await text("h1")).includes("92104"), "core ZIP h1");
    expect(await page.locator(".recharts-surface").count() > 0, "no ZIP charts");
    await go("/zip/92037");
    await noSample();
    expect((await text("h1")).includes("La Jolla"), "covered ZIP h1");
    await go("/zip/00000");
    expect((await body()).includes("don't cover"), "uncovered ZIP message");
  });
  await step("tools-themes-legal", async () => {
    await go("/tools");
    await noSample();
    for (const name of ["Sage Linen", "Cocoa Night", "Harbor Dusk", "Desert Clay"]) {
      await page.getByRole("button", { name: new RegExp(name) }).first().click();
      await page.waitForTimeout(250);
    }
    expect((await page.evaluate(() => document.documentElement.dataset.theme)) === "desert-clay", "theme switch");
    await go("/privacy");
    expect((await text("h1")).includes("Privacy"), "privacy h1");
    await go("/terms");
    expect((await text("h1")).includes("Terms"), "terms h1");
    await go("/about");
    await noSample();
    expect((await body()).includes("Privacy"), "about doesn't link Privacy");
  });
  await step("mobile", async () => {
    await page.setViewportSize({ width: 375, height: 812 });
    for (const p of ["/", "/find", "/saved", "/alerts", "/renter", "/zip/92037"]) {
      await go(p);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over <= 1, `${p} scrolls sideways by ${over}px at 375`);
    }
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  await browser.close();
  const bad = results.filter((r) => !r.ok);
  writeFileSync(join(OUT, "e2e-results.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), results }, null, 2));
  console.log(`\n${results.length - bad.length}/${results.length} feature steps passed against ${BASE}`);
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
