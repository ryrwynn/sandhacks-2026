# RentOrKnot design brief: apartment tracker first

RentOrKnot leads with one job: **save apartments you like and watch their asking rent over time.** The engine stays: the fair-rent check, the AB 1482 rent check, ZIP forecasts and the persona finders all keep working, and they show up inside the tracker where they help (a "typical range" label on every apartment, a forecast band on market charts, a rent-check link on an apartment's page). Renter, Buyer and Owner tools move under one "Tools" entry instead of being the home page.

Sources: the Figma prototype (one frame, "Rental market overview", grayscale wireframe) and rynn's code on `main` (`frontend/src/app/{page,find,saved,alerts}`, `components/{ApartmentCard,Sparkline,RentChart,FilterBar,NavBar}`, `lib/{saved.tsx,types.ts}`), which implements that frame with mock data. Use rynn's components as the base, wire them to real data, and restyle them with the palette below.

## Navigation

One top bar for the whole site (merge `NavBar` and `ModeNav`):

- Brand at left: **RentOrKnot**, matching the domain rentorknot.us (the Figma's "SandHacks" is a placeholder).
- Market overview (`/`) · Saved apartments (`/saved`) · Price alerts (`/alerts`) · Find apartments (`/find`) · Tools ▾ (Rent increase check, Buy, Own, About, and the newer tools).
- Saved apartments shows a count badge; Price alerts shows a badge when a saved apartment hit its target.
- An optional "Sign in" (Google) button appears only when sign-in is configured; it links to `/privacy`. Without it the site works fully with local saves.
- A small footer on every page: Privacy · Terms · About.
- Under 768px wide: the four main destinations move to a bottom tab bar with icons and labels; Tools stays in the top bar.

## Market overview (`/`), from the Figma frame

Top to bottom:

1. **Heading** "Rental market overview", subline "See how asking rents change over time, then track the places you love." Right side: "Updated weekly · last {last scrape date}" from `/api/health` (Zillow rentals refresh every Thursday).
2. **Filter row:** area (the plan's 12 ZIPs, shown by neighborhood name with the ZIP), bedrooms (Any, Studio, 1, 2, 3+), property type (All, Apartment, Condo, House), "More filters" (max price), and at the right a date-range picker.
3. **Market card:** label "Average asking rent", big number "$2,850 / month", then "+5.6% since {start month}" and "Across {n} active listings". Range toggles at top right: 1M · 3M · 6M · 1Y · All. A line chart with light horizontal gridlines, month ticks, the current value in a dark tag at the right end, and a footnote "USD / month · Monthly averages". Add the 12-month forecast as a dashed line with its 80% band and the backtest error under the chart (the plan's rule), and a hover/tap tooltip with the month and value.
4. **Saved apartments row:** "Saved apartments · {n} tracked", subline "Your watchlist, with asking-rent history at a glance.", a primary "+ Save apartment" button that goes to `/find`, four apartment cards, and "View all saved apartments →" at the bottom right.
5. Below that, a smaller ZIP map section (the existing Mapbox `ZipMap`) titled "Compare neighborhoods", linking each ZIP to `/zip/[zip]`.

Where the chart's numbers come from: with "Any" bedrooms, the ZIP's Zillow typical rent (ZORI, labeled as such); with a bedroom count, monthly medians of asking rents from our listings and their price-history events, with the listing count shown. If a month has fewer than 5 listings, fall back to ZORI and say so under the chart. Never fill a gap with made-up points.

## Apartment card (used on `/`, `/saved`, `/find`)

From the Figma card, top to bottom:

- Address (bold) and a round link button at top right that opens the source listing in a new tab (only for listing-site records with a public URL; never for social posts).
- "{Neighborhood} · {beds} bed · {sqft} sq ft" (Studio for 0 beds).
- Price "$2,950 / mo" (always with a thousands separator), and at right the change since tracking started: "↓ $100 (3.3%)". Drops use the "good" color, rises the "warn" color, and the arrow and words always say which way, so color is never the only signal.
- A sparkline of real price observations, with the first and last observation months under it. With a single observation, show a dot and "Tracking since {date}".
- New: a small label from the fair-rent engine: "In typical range", "Above typical range" or "Below typical range" (never "illegal").
- Tags from real data only, at most 4 after the fair-rent label: the listing's amenities (filled chips), then area tags about the ZIP (outlined, always ending "(ZIP)", e.g. "Groceries nearby (ZIP)"). Facebook rooms carry "Roommate wanted" and sublets "Sublet".
- Facebook listings: a "Facebook group · lower confidence" badge, the group name, a title built from extracted fields (no street address), and a "View post on Facebook" link.
- On `/find`: a full-width "+ Save apartment" / "Saved ✓" toggle, always at the bottom of the card (cards in a row are equal height, so the buttons line up). On saved cards: a remove action in a small menu.
- The whole card links to the apartment page.

## Apartment page (`/apartments/[id]`, new)

- Header: address, neighborhood, beds, baths, sqft, property type, year built if known, Save toggle, source link.
- **Price history chart:** a step line (asking rent changes in steps) over every real observation, with event markers for Listed, Price change and Removed, and a table of the same events below it.
- "What it should rent for": the fair-rent estimate with its range and label, and its percentile among comparable listings (same ZIP and bedrooms).
- Neighborhood context: the ZIP's 12-month rent forecast with its band, linking to `/zip/[zip]`.
- "Renting here already?": a link to the rent increase check, prefilled with the address and year built.

## Saved apartments (`/saved`)

The full watchlist as a card grid, sortable by most recently saved, price, and biggest drop since saved. Each saved item remembers the price when it was saved, so cards can say "↓ $75 since you saved it". Empty state: "Nothing saved yet. Find apartments to start a watchlist." with a button.

Multi-select: shift-click or Ctrl/Cmd-click cards, or turn on "Select" mode (checkboxes, for touch and screen readers). An action bar offers "Open selected in new tabs" (links that the browser blocks are listed to open by hand), "Remove selected" (with an undo toast) and "Clear"; Escape clears the selection.

On the first visit only, seed four real apartments that have at least three price observations, marked "Example: remove anytime", so the demo never opens on an empty page.

## Price alerts (`/alerts`)

In-app only. For each saved apartment the user can set a target rent. The page lists saved apartments whose price dropped below their target or changed since the last visit, newest first, and the nav badge counts them. No email, SMS or push: the app never sends messages, and it collects no contact details.

## Find apartments (`/find`)

The filter row (with max price, source: all / listing sites / Facebook groups, and unit: whole units, "Roommate wanted (rooms)", sublets), a collapsible "Not sure where to look?" panel holding the Starter finder (ranked ZIPs for a budget; "Show listings in {area}" sets the area filter), a results bar "{n} apartments in {area}" with sort (Recommended, Price low to high, Price high to low, Biggest price drop), and the card grid with save toggles. Paginate or load more past 24 results. Empty state suggests widening the filters.

## Saving (local first, optional sign-in)

Saved apartments and alert targets live in the browser's `localStorage` (extend rynn's `SavedProvider`): `{ id, savedAt, priceAtSave, target? }` per listing id. Wrap every read and write in try/catch, and render correctly when storage is empty or blocked. Without sign-in nothing about the user is sent to or stored on the server. Optional Google sign-in (docs/ACCOUNTS.md) syncs the same items keyed by a salted hash of the Google account ID; no email or name is stored. `/privacy` and `/terms` explain this in plain language.

## Visual style

Palette (coolors.co cb997e-ddbea9-ffe8d6-b7b7a4-a5a58d-6b705c) with the text shades derived from it. Contrast ratios were checked against WCAG; keep them at least this high.

| Token | Hex | Use | Contrast |
| --- | --- | --- | --- |
| `--bg` | `#FFE8D6` | Page background | |
| `--surface` | `#FFFAF5` | Cards, nav, inputs (a tint of `#FFE8D6`) | |
| `--line` | `#DDBEA9` | Borders, dividers, chips (ink text on chips) | ink on it 7.6:1 |
| `--grid` | `#B7B7A4` | Chart gridlines, inactive series | not for text |
| `--sage` | `#A5A58D` | Secondary fills, the forecast band edge | not for text |
| `--accent` | `#CB997E` | Highlights, selected filters, the current-value dot, map shading; ink text only on it | ink on it 5.3:1 |
| `--accent-strong` | `#8F5A3F` | Accent text and thin accent lines (forecast line) | 4.8:1 on bg, 5.5:1 on surface |
| `--primary` | `#6B705C` | Primary buttons (white text), the main chart line, active nav underline | white on it 5.1:1 |
| `--primary-hover` | `#4E5341` | Button hover | |
| `--ink` | `#2E3127` | Body text and headings | 11.2:1 on bg |
| `--muted` | `#5C604F` | Secondary text | 5.5:1 on bg |
| `--good` | `#4E5341` | Price drops, "within cap" | 6.7:1 on bg |
| `--warn` | `#8C3B22` | Price rises, "over cap", errors | 6.4:1 on bg |

- Charts: history line `--primary` 2px, forecast dashed `--accent-strong`, 80% band `--line` at about 60% opacity, gridlines `--grid` at low opacity, value tag `--ink` with white text.
- Map: shade ZIPs from `--bg` through `--line` and `--accent` to `--accent-strong` (lighter = cheaper), with a legend.
- Friendlier feel: 12px card radius, soft shadow instead of hard borders on cards, 16px base text on phones, at least 44px tap targets, generous spacing, plain-language labels ("asking rent", "since you saved it"), skeleton loaders, and helpful empty states. Keep the Figma's clean sans font.
- Every page works at 375px wide with no horizontal scroll; focus outlines are visible (`--primary`, 2px).
- The renter, buyer, owner, ZIP and about pages get the same tokens and components, so the whole site looks like one product.
