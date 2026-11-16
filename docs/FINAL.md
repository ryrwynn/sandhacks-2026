# Final run: what you do first, then the prompt

## Part 1: before you paste the prompt

**Already done (2026-11-15):** OAuth client created; both redirect URIs confirmed with Google (a control URI is
rejected). GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, AUTH_SECRET and ACCOUNT_API_TOKEN are in the local `.env`, and with
BRIGHTDATA_BUDGET_USD=10, ONDEMAND_DAILY_USD=1 and LLM_EXTRACT_MAX_PER_RUN=40 also in the server's `.env` (through
`scripts/server-env.sh`; backup kept on the server; nothing restarted).

Decisions (filled into the prompt below): Zillow weekly on Thursdays at 4:00 AM Pacific; Facebook `terms_checked_on`
kept; Penal Code 396 160% rule verified; Google sign-in keys set.

Also done: consent screen published (In production, External); database reachable from the laptop again; contact
email chosen; PR #1 decision made (everything goes into it).

Still yours (items 1, 3 and 5 below are done; kept for reference):

1. **Database access from this laptop.** Since about 07:00 the laptop can't open a TCP connection to Tiger (DNS
   works and the live site is fine). Switch network or VPN, or add your IP to the service's allow list in the Tiger
   console. Check: `uv run python -c "import os,psycopg; psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=8); print('ok')"`
2. **Consent screen published.** Google Cloud → APIs & Services → OAuth consent screen → Publish app (in Testing mode
   only listed test users can sign in). After the deploy, add `https://rentorknot.us/privacy` and
   `https://rentorknot.us/terms` there as the privacy policy and terms links.
3. **A contact email for the privacy and terms pages** (removal requests for Facebook-derived listings, questions).
   Fill the blank in the prompt. Use a project address, not a personal one, if you have one.
4. **The 160% rule vs. the FMR figures.** "Verified" lets the 160%-of-Fair-Market-Rent rule give firm answers, but
   the FMR numbers in `api/rules/data/fmr.yaml` come from a third-party mirror and are still marked unverified, so
   that path stays "unclear" until someone downloads HUD's FY2026 Small Area FMRs (huduser.gov refused automated
   downloads). The prompt tries; if it's refused, download the file yourself and drop it in `api/rules/data/`.
5. **PR #1.** Merging `night` into `Setup` puts all of it into PR #1 (Setup → main). Merge or close PR #1 first if
   you want them kept separate.
6. Load `.env` into a fresh terminal, then start the session there.

Cost after this run: Zillow rentals weekly ≈ 1,777 records × 4.35 ≈ 7,700 records ≈ **$11.60/month** (was ≈ $640);
`zillow_sale` daily ≈ $11/month (unchanged); Facebook Monday/Thursday ≈ $3.90/month.

## Part 2: the prompt (start a fresh session on branch `night`, after loading `.env` into the shell)

```text
You are the final pre-merge orchestrator for RentOrKnot (rentorknot.us). Read CLAUDE.md, docs/WAKEUP.md,
docs/FINAL.md, docs/STATUS.md, the "Safety rules" in docs/NIGHT.md, and docs/DESIGN.md. Read only the
sections of docs/PLAN.md you need. You're on branch night (draft PR #2 into Setup). Work unattended through
step 10, then stop and wait for "go".

Keys are environment variables. Never read or print .env, never run env, printenv or set, never echo a
variable that holds a key or a connection string. Until I say go: never push to Setup or main, never merge
PR #2, never change deploy.yml or GitHub secrets, and touch the server only through scripts/. Keep
docs/STATUS.md current (new "Final run" section with a heartbeat). If the same error repeats twice, stop that
thread and note it. Use lane subagents (Sonnet, own worktrees) for independent UI work if it helps; merge
them into night yourself.

My decisions:
- Zillow rentals: weekly, Thursdays 4:00 AM Pacific.
- Facebook: keep sources.facebook_groups_sd.terms_checked_on as it is.
- Penal Code 396: the 160%-of-Fair-Market-Rent rule is verified.
- Google sign-in: keys are set (local and server .env).
- Contact email for /privacy and /terms: none (removed in the sprint; the pages show no address)
- PR #1: fine for night to land in PR #1 (Setup -> main); no separate handling.

1. Connectivity. Check the database (8-second connect timeout). If it fails, stop and tell me.

2. Schedules and rules.
   - docker/worker.crontab: zillow_rent once a week, Thursday 12:00 UTC (4:00 AM PST; note that it becomes
     5:00 AM during daylight time). Keep zillow_sale and the train job as they are. The listing "active"
     window is relative to each source's latest scrape, so check it still works with a weekly scrape and that
     Price alerts still make sense; adjust the wording ("Updated weekly") where the UI says "every few hours".
   - api/rules/gouging.py: FMR_RULE_VERIFIED = True; update tests, MORNING.md and MODEL/rules notes. Try once
     to download HUD FY2026 Small Area FMRs for San Diego ZIPs; if it works, load them marked verified with
     the source; if refused, leave fmr.yaml unverified (that path keeps answering "unclear") and say so.
   - Put the new monthly Bright Data estimate in WAKEUP.md from Bright Data's snapshot list (dataset_size).

3. Facebook: roommate offers and the full run.
   - Fix api.llm.gemini.parse_posts: a post that offers a room in a shared home ("roommate wanted", "room for
     rent") is a rental offer with unit_type 'room'; a post by someone looking for a place or a room is not
     (those are people, not listings, and stay out). Add a flag roommate_wanted to the fields.
   - Re-extract the paid full run without scraping again:
     uv run python -m worker.facebook collect --snapshot sd_mwhxcv0l15owbti9eg
     (the prompt change means new Gemini calls, about 35 Flash Lite requests; fine). Re-extract the sample's
     raw records the same way only if they were dropped as non-offers.
   - Report groups, posts, usable share, whole units, rooms, sublets, roommate-wanted and unusual prices.
   - Never replay to shared yet.

4. Live-query safety. Before any replay to shared, the live API must not leak areas outside data/zips.txt:
   filter the zip_features usage and the market, listing, median and comparable queries in api/db.py to the 12
   ZIPs (the index tier stays in staging_area_metrics). Add a test.

5. Fixes from my partner (smallest change first; keep 375px with no horizontal scroll and 44px tap targets):
   a. Buy (keep it in Tools): every number on /buyer shows at most 2 decimals; ratios shown as percentages;
      check the Gemini summary has no raw decimals (already sends only labels) and the contribution rows.
   b. Tools > Rent increase check: remove the "Find a place" tab. Don't lose the Starter finder: move it into
      /find as a collapsible "Not sure where to look?" panel whose ranked ZIPs set the Find area filter when
      clicked, so it is connected to the listings.
   c. Find cards: the Save button sits at the bottom of every card, in the same place whether or not the card
      has tags (flex column, the button pushed down with mt-auto; equal-height cards in a grid row).
   d. Favicon: use the RentOrKnot logo (frontend/public/brand/logo.svg) as app/icon.svg plus an
      apple-icon.png; remove the default favicon.ico.
   e. Find cards get more tags from real data only:
      - listing amenities: Zillow unit_amenities (extras.amenities) and Facebook's extracted ones (parking,
        laundry, pets allowed, utilities included);
      - ZIP-level features from zip_features (groceries, transit stops, parks), labelled honestly as area
        tags, e.g. "Groceries nearby (ZIP)", shown when the ZIP is in the top third of the 12 ZIPs per km²;
      - at most 4 tags per card, plus the fair-rent label. Add the needed fields to the listings API
        (contract change, fixtures, regenerated types; say why in the commit).
   f. Saved apartments multi-select: shift-click (and Ctrl/Cmd-click) on cards to select several; a
      keyboard-accessible "Select" mode with checkboxes for touch and screen readers; an action bar with
      "Remove selected" (with an undo toast) and "Open selected in new tabs". Browsers block more than one
      window.open per click: open them from one click in a loop and, if any were blocked, show the list of
      links to open. Escape clears the selection.
   g. Extra feature: Facebook rooms show a "Roommate wanted" tag next to the fair-rent label (and sublets
      "Sublet"); Find's unit filter gets "Roommate wanted" as the label for rooms.

6. Privacy and terms pages: /privacy and /terms, linked from the footer, /about and the sign-in button.
   Plain language, no legal claims we can't back:
   - /privacy: saves live in the browser (localStorage); optional Google sign-in stores only a hash of the
     Google account ID (sha256 with a server secret) and the saved listings, never an email or name; how to
     delete them (sign out and clear, or ask by email); no ads, no tracking, no data sold; what we collect from
     public sources (Zillow listings, Zillow Research, Census, OpenStreetMap, public Facebook groups) and that
     Facebook-derived listings keep only extracted fields and a link to the post (post text, names, profile
     links and photos are never stored); how to request removal of a Facebook-derived listing (contact
     email); Gemini processes post text and form text you submit; server logs; contact.
   - /terms: informational only, not legal, financial or real-estate advice; estimates can be wrong; listings
     come from third parties and may be out of date; we never contact landlords or post anything; acceptable
     use (no scraping, no abuse of the forms); no warranty and limited liability; California law; changes;
     contact. Mark both "Last updated" with today's date and add a note in WAKEUP.md that a lawyer hasn't
     reviewed them.
   - Both pages need an h1 and pass the UI check.

7. Docs: update docs/PLAN.md and docs/DESIGN.md to match what is now true (Facebook listings with post links
   and price history, rooms and roommate tags, source breakdown and weighting, optional Google sign-in,
   privacy/terms pages, Starter finder inside Find, weekly Zillow), and docs/ACCOUNTS.md step 2 (with sign-in
   off /auth/session answers {"enabled": false}).

8. Checks, all must pass:
   - ./scripts/preflight.sh (report its output; don't change what it checks)
   - uv run pytest api/tests -q (add tests for every new behavior: roommate extraction, area tags, ZIP filter)
   - cd frontend && npm run build && npx tsc --noEmit
   - API on :8000 with RENTORKNOT_READ_STAGING=1 and the production build on :3000 in the background (PIDs in
     STATUS.md), then node scripts/ui-check.mjs against http://localhost:3000, with /privacy and /terms added
     to its page list. Extend it (page loads only, never submit a form): pan the home map at 375px from San
     Diego toward Orange County and confirm county shapes load; check each theme's first paint (no flash) and
     that a first visit with prefers-color-scheme dark gets Cocoa Night; on /saved, shift-click two cards and
     check the action bar appears (don't press Remove). Rerun until every load passes. Look at the
     screenshots for Find (tags, aligned Save buttons, Starter panel), Find filtered to Facebook, a Facebook
     room, a ZIP page with Facebook data, /saved with a selection, /buyer, /gouging, /privacy and /terms.
   - Run the read-only capacity SQL in docs/TIGER_CAPACITY.md and add the numbers there.
   - Google sign-in: with the keys loaded, check /auth/session answers with no email or name, the button
     appears, and a wrong ACCOUNT_API_TOKEN fails quietly. Leave the real sign-in to me.

9. Stop the local servers, commit, push night, mark PR #2 ready for review (do not merge), and update
   docs/WAKEUP.md: results, costs, Facebook counts, anything not done, and a short "ready to merge" checklist.

10. Stop and wait.

When I say go:
   a. Merge PR #2 into Setup.
   b. Fetch, then follow the deploy with ./scripts/watch-deploy.sh $(git rev-parse origin/Setup) until the
      smoke test passes.
   c. Only then: uv run python -m worker.facebook replay --target shared --confirm-shared (12 ZIPs only).
   d. Run ./scripts/smoke.sh https://rentorknot.us and node scripts/ui-check.mjs https://rentorknot.us.
   e. Fix forward on Setup. If the live site isn't passing within 30 minutes or two fix attempts, revert the
      merge on Setup (git revert -m 1), push, confirm the previous site is back, and report.
   f. Tell me to sign in with Google on the live site once (docs/ACCOUNTS.md steps 3 to 7) and to add the
      /privacy and /terms links to the Google consent screen.

Rules: the app only reads and analyzes; never post to any site. Stay within BRIGHTDATA_BUDGET_USD and
Gemini's free tier. This run needs no new Bright Data scrape.
```
