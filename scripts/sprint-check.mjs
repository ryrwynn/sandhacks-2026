#!/usr/bin/env node
// Sprint checks before "go" (docs/SPRINT.md, "Checks before go"), the browser parts beyond ui-check and e2e.
// Usage: node scripts/sprint-check.mjs [BASE_URL]   (default http://localhost:3000; API reachable at BASE/api)
// Read-only: it never submits a form (it checks that no form submits on its own).
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const { chromium } = createRequire(join(here, "package.json"))("playwright");
const BASE = (process.argv[2] || process.env.SPRINT_BASE_URL || "http://localhost:3000").replace(/\/$/, "");
const results = [];

async function check(name, fn) {
  let err = null;
  try { await fn(); } catch (e) { err = String(e.message || e).split("\n")[0].slice(0, 300); }
  results.push({ name, ok: !err, err });
  process.stdout.write(`${err ? "FAIL" : "ok  "} ${name}${err ? `\n      - ${err}` : ""}\n`);
}
const expect = (c, m) => { if (!c) throw new Error(m); };
const api = async (path) => (await fetch(`${BASE}/api${path}`)).json();

const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
const newPage = async (width = 1280, height = 900) => {
  const ctx = await browser.newContext({ viewport: { width, height } });
  return { ctx, page: await ctx.newPage() };
};

// 1. Sidebar against the left edge.
for (const w of [1280, 1920]) {
  await check(`sidebar touches the left edge at ${w}px`, async () => {
    const { ctx, page } = await newPage(w);
    await page.goto(`${BASE}/find`, { waitUntil: "domcontentloaded" });
    const box = await page.locator("aside").first().boundingBox();
    await ctx.close();
    expect(box && box.x <= 0.5 && box.width > 0, `aside starts at x=${box?.x}`);
  });
}

// 2. Sidebar order and renamed headings and titles.
await check("sidebar order: Find by needs, Rent Cap, Emergency Rent Limits first", async () => {
  const { ctx, page } = await newPage();
  await page.goto(`${BASE}/find`, { waitUntil: "domcontentloaded" });
  const links = (await page.locator('aside nav[aria-label="Tools"] a').allInnerTexts()).map((t) => t.split("\n")[0].trim());
  await ctx.close();
  expect(links[0] === "Find by needs" && links[1] === "Rent Cap" && links[2] === "Emergency Rent Limits", `order: ${links.slice(0, 4).join(" | ")}`);
});
for (const [path, h1, title] of [["/renter", "Rent Cap", "Rent Cap | RentOrKnot"], ["/gouging", "Emergency Rent Limits", "Emergency Rent Limits | RentOrKnot"]]) {
  await check(`${path} heading "${h1}" and title "${title}"`, async () => {
    const { ctx, page } = await newPage();
    await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded" });
    const got = (await page.locator("h1").first().innerText()).trim();
    const t = await page.title();
    await ctx.close();
    expect(got === h1 && t === title, `h1 "${got}", title "${t}"`);
  });
}

// 3. Facebook card: link button top right, badge in the tags.
await check("Facebook card: round link button top right, badge in the tags row, no bottom text link", async () => {
  const { ctx, page } = await newPage();
  await page.goto(`${BASE}/find?source=facebook`, { waitUntil: "domcontentloaded" });
  const btn = page.locator('a[aria-label^="Open the Facebook post for"]').first();
  await btn.waitFor({ timeout: 30000 });
  const card = btn.locator("xpath=ancestor::article[1]");
  const cb = await card.boundingBox(), bb = await btn.boundingBox();
  const tagText = await card.locator('ul[aria-label="Tags"]').innerText();
  const bottom = await page.getByText("View post on Facebook").count();
  await ctx.close();
  expect(cb && bb && bb.x + bb.width > cb.x + cb.width * 0.75 && bb.y < cb.y + cb.height * 0.3, "button not at top right");
  expect(/Facebook group/.test(tagText), `tags: ${tagText.replace(/\n/g, ", ")}`);
  expect(bottom === 0, "bottom text link still there");
});

// 4. Saved: open sources, remove, undo.
await check('Saved: "Open sources in new tabs" opens source URLs; "Remove from saved" + Undo restores both', async () => {
  const fb = (await api("/listings?limit=1&source=facebook")).items[0];
  const zl = (await api("/listings?limit=1&source=listing_sites")).items[0];
  expect(fb && zl, "need one Facebook and one listing-site listing");
  const { ctx, page } = await newPage();
  const opened = [];
  await ctx.route(/facebook\.com|zillow\.com/, (r) => { opened.push(r.request().url()); return r.fulfill({ status: 200, body: "stub" }); });
  await page.goto(`${BASE}/saved`, { waitUntil: "domcontentloaded" });
  const now = new Date().toISOString();
  await page.evaluate(([a, b, t]) => localStorage.setItem("rentorknot:saved:v1", JSON.stringify({ seeded: true, items: [
    { id: a.id, savedAt: t, priceAtSave: a.current_price_usd }, { id: b.id, savedAt: t, priceAtSave: b.current_price_usd }] })), [fb, zl, now]);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Select", exact: true }).click();
  const boxes = page.locator('main input[type="checkbox"]');
  await boxes.first().waitFor({ timeout: 30000 });
  for (let i = 0; i < await boxes.count(); i++) await boxes.nth(i).check();
  await page.getByRole("button", { name: /Open sources in new tabs/ }).click();
  await page.waitForTimeout(2500);
  const want = [fb.post_url, zl.source_url].filter(Boolean);
  expect(want.every((u) => opened.some((o) => o.startsWith(u.split("?")[0]))), `opened ${opened.length}: ${opened.join(" ")}`);
  await page.bringToFront();
  await page.getByRole("button", { name: /Remove from saved/ }).click();
  await page.getByRole("button", { name: /Undo/ }).click();
  await page.waitForTimeout(500);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("rentorknot:saved:v1") || "{}").items?.map((i) => i.id) || []);
  await ctx.close();
  expect(stored.includes(fb.id) && stored.includes(zl.id), `after undo: ${stored}`);
});

// 5. Every form fills from its prefill link and doesn't submit.
const forms = [
  ["/renter?address=123%20Main%20St&zip=92104&lowest=2000&new=2300&effective=2026-12-01&year=1990", ["123 Main St", "92104", "2000", "2300", "2026-12-01", "1990"]],
  ["/renter?tab=listing&zip=92104&beds=1&asking=2400&sqft=650", ["92104", "2400", "650"]],
  ["/gouging?zip=92104&beds=1&new=2600&date=2026-11-01&before=2300", ["92104", "2600", "2026-11-01", "2300"]],
  ["/owner?zip=92104&beds=2&target=3100&sqft=900&year=1985", ["92104", "3100", "900", "1985"]],
  ["/owner/reach?zip=92104&beds=1&ask=2300&text=Sunny%20unit%20with%20parking", ["92104", "2300", "Sunny unit with parking"]],
  ["/buyer?budget=750000&beds=2", ["750000"]],
  ["/find?zip=92104&beds=1&max=3000&starter_budget=2600&starter_beds=1", ["92104", "3000", "2600"]],
  ["/advisor?needs=quiet%201%20bedroom%20near%20transit&ask=Is%20North%20Park%20a%20good%20fit", ["quiet 1 bedroom near transit", "Is North Park a good fit"]],
];
for (const [url, want] of forms) {
  await check(`prefill ${url.split("?")[0]}${url.includes("tab=listing") ? "?tab=listing" : ""} fills and doesn't submit`, async () => {
    const { ctx, page } = await newPage();
    const posts = [];
    page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/api/")) posts.push(r.url()); });
    await page.goto(`${BASE}${url}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);
    const values = await page.evaluate(() => [...document.querySelectorAll("input, textarea, select")].map((e) => String(e.value).replace(/[$,]/g, "")));
    await ctx.close();
    const missing = want.filter((w) => !values.some((v) => v === w || v.includes(w)));
    expect(!missing.length, `not filled: ${missing.join(", ")}`);
    expect(!posts.length, `submitted on its own: ${posts.join(" ")}`);
  });
}

// 6. Find: Max price visible, 15 per page, Per page, page 2 differs, filter back to page 1, staged county ZIPs listed.
await check("Find: Max price visible, 15 per page, Per page changes it, page 2 differs, filter -> page 1", async () => {
  const { ctx, page } = await newPage();
  await page.goto(`${BASE}/find`, { waitUntil: "domcontentloaded" });
  expect(await page.getByLabel("Max price").isVisible(), "Max price not visible");
  const showing = page.getByTestId("find-showing");
  await showing.waitFor({ timeout: 45000 });
  expect(/^Showing 1–15 of/.test(await showing.innerText()), await showing.innerText());
  const titles = async () => (await page.locator("main article h3, main article h2").allInnerTexts()).join("|");
  const p1 = await titles();
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForFunction(() => /Showing 16–/.test(document.querySelector('[data-testid="find-showing"]')?.textContent || ""), null, { timeout: 45000 });
  expect(new URL(page.url()).searchParams.get("page") === "2", `url ${page.url()}`);
  expect((await titles()) !== p1, "page 2 shows the same listings");
  await page.getByLabel("Bedrooms").selectOption({ index: 2 });
  await page.waitForFunction(() => /Showing 1–/.test(document.querySelector('[data-testid="find-showing"]')?.textContent || ""), null, { timeout: 45000 });
  await page.locator("select").filter({ has: page.locator('option[value="30"]') }).last().selectOption("30");
  await page.waitForFunction(() => /Showing 1–30 /.test(document.querySelector('[data-testid="find-showing"]')?.textContent || ""), null, { timeout: 45000 });
  await ctx.close();
});
await check("area dropdown lists the staged county ZIPs (RENTORKNOT_READ_STAGING=1)", async () => {
  const zips = (await api("/zips")).zips.filter((z) => z.tier === "county");
  expect(zips.length > 0, "/zips has no county ZIPs");
  const { ctx, page } = await newPage();
  await page.goto(`${BASE}/find`, { waitUntil: "domcontentloaded" });
  const group = page.locator('select[aria-label="Area"] optgroup[label="San Diego County"]');
  await group.waitFor({ state: "attached", timeout: 30000 });
  const n = await group.locator("option").count();
  await ctx.close();
  expect(n === zips.length, `dropdown county options ${n}, /zips county ${zips.length}`);
});

await browser.close();
const bad = results.filter((r) => !r.ok);
console.log(`\n${results.length - bad.length}/${results.length} sprint checks passed against ${BASE}`);
process.exit(bad.length ? 1 : 0);
