# Work log

Newest first. One entry per change: date, who, what, and anything the other person should know.
Mark unfinished work **IN PROGRESS** (with the files it touches) and update the entry when it's done.

## 2026-10-30, cmags0511 (Claude, research run)
`merge_notes.py`: anytime-TD notes are also accepted for keys on the app's Top anytime-TD list (`picks.json` tdTop), not only packet `td_candidates`. Games without a packet (this week LAR) had their audit fix notes dropped as unknown keys. No ranking change.

## 2026-10-29 (4), cmags0511 (Claude)
- Record: `record.py` now drops rows that were only ever on the retired overs-only Top 10 (42 rows removed from `record.json`, 310 -> 268); the page already ignored them. tune.py loses those 42 graded picks as training rows.
- Late availability: `lines.yml` also runs every 20 minutes on NFL game days (Sunday 10am-6pm ET, Mon/Thu night windows) so ESPN's inactives reach the picks and the record lock sooner than the hourly :47 run. Questionable pills on NFL cards now read "Q · plays ~56%" (NFL skill players listed Questionable played 56% of the time, 2023-25). `sw.js` is pt-v122.
- Tackle/sack prices: fetch_odds.py already asks The Odds API for `player_tackles_assists` and `player_sacks`; they stay unpriced (graded at an assumed -110, flagged) until an `ODDS_API_KEY` secret is set.

## 2026-10-29 (3), cmags0511 (Claude)
All tab: a "Grades" box under the intro lists each grade, its expected-return range and the units it stakes (A 2u, B 1u, C 1/2u, D pass, F avoid; 1 unit = 1% of bankroll) and what the "-" chip means. Front end only (`gradeKeyHtml` in index.html); `sw.js` is pt-v121.

## 2026-10-29 (3), cmags0511 (Claude, research run)
`picks.py`: the anytime-TD loop skips note keys that don't have 3 parts. The soccer team-bet keys (`SOCT|...`, added Oct 28)
made `picks.py` crash with "too many values to unpack" whenever the soccer researcher wrote notes. No change to rankings.

## 2026-10-29 (2), cmags0511 (Claude)
Top 10 audit (215 graded picks since Oct 17, 107-108, -15.7u): the NBA is the whole loss (51-61, -16.8u, already paused until Nov 15);
the lowest-scored half lost 13.5u while the top quarter broke even; plus-money picks went 2-11 (-8.7u) vs 9-4 at -150 or shorter.
`picks.py`: the Top 10 now needs a score of at least `MIN_TOP_SCORE` = .23 (was .12; .27 was tried first, then eased a little) and plus-money picks rank at `PLUS_PEN` = .8 of their
score. On today's data the list shrinks from 30 candidates to about 16 (all NFL). The cutoff was fitted on the same sample, so re-check after
another month of graded picks. Prop-type slices (rushing yards, combos) left alone: samples too small. Front end: Top 10 picks the books don't list (tackles, sacks, some receptions) still grade at an assumed -110 but are now flagged in the record ("-110 assumed" on recent rows, a count and their units in the footer); `sw.js` is pt-v120. byMarket,
games and overs lists keep their own floors.

## 2026-10-29, cmags0511 (Claude)
Added `backtest_soccer_odds.py`, `backtest_nfl_sources.py` and `backtest_nba_sources.py` (and a README note) so the source tests behind
the Oct 28 soccer change are reproducible. They only read public data and write into a `backtest_data/` folder (git-ignored); nothing
in the app, workflows or data files changes.

## 2026-10-28 (night), cmags0511 (Claude)
Soccer research check. `research_packets.py` `soccer_packet` now builds `SOCCER-day` from the soccer bets that are recorded: the
Top picks / Value bets players (it was reading the retired lists) plus the team bets, grouped by match under `matches`
(keys `SOCT|` + the bet's key). `merge_notes.py` accepts those keys. `RESEARCH.md`: the soccer researcher is back (about 15
searches, one agent) and its brief now covers team bets (key players out, rotation, fixture congestion). `index.html`: a team
bet's reasoning sheet shows the note (or "No research on this match yet"), and the card gets a "news" tag on a caution.
Display only: the notes don't change which bets are listed or recorded. The scheduled research task on the owner's account
reads RESEARCH.md, so it picks the change up on its next run. `sw.js` -> pt-v119.

## 2026-10-28 (night, 2), cmags0511 (Claude)
Soccer team bets: `soccer_team.py` removes Pinnacle's margin with Shin's method instead of proportionally, and drops main-market
bets with more than 6% claimed edge (`EV_MAX_MAIN`). Backtested on 24,600 matches of football-data.co.uk odds (see README, Soccer).
On live prices this cut the list from 14 to 8 bets (the biggest "edges", e.g. Fortuna Sittard double chance +500, are gone).
Model-only bets (5% minimum, +300 cap) are unchanged: the backtest only covered main markets. No front-end change.

## 2026-10-28 (late), cmags0511 (Claude)
Soccer record cleanup. Removed the retired lists' rows from `record.json` (Goalscorers, Plus money, old Best value: 113 rows). The
current player-prop lists (Top picks, Value bets) are recorded again: `record.py` no longer stops at Oct 28 and only reads the
`top` and `value` lists. The Soccer record keeps the List filter (Team bets / Most likely / Value bets); the "Retired lists"
option and rows are gone. `sw.js` -> pt-v118.

## 2026-10-28
- **cmags0511** (PR, via Claude): Soccer tab rework, front end only (`index.html`, `sw.js` pt-v116; no data, model or grading change).
  (1) Soccer now has two sections like NFL: **Top picks** (Team bets, Most likely players and Value bets as separate groups
  in the same card layout as the NFL Top picks: grade line, "See my reasoning" sheet, Track on player props) and **Matches**
  (one card per match with its team bets and best picks, tap for every bet). Dropdowns for section, bet type and league
  replace the three-way toggle and league chips; the old team-bet card markup was squished by the redesign and is gone.
  (2) Record tab > Soccer now counts the team bets (soccer_team.json) together with every player-prop list (retired ones
  too), and is filterable: List, League, Result, Book plus the existing Odds / App's chance / Value / Prop / Dates, a
  Breakdown table by list / league / bet type / book where tapping a row filters the record to it, and team bets in the pick
  log with their scores. Soccer-only filters clear when you switch sport. The headline for Soccer changed meaning: it was
  Top picks + Value bets since Oct 19; it is now everything recorded (85-121 on Oct 28), narrow it with the List filter.
  The All record page's soccer table gains a Team bets row. Touches renderSoccer/socPickCard/socMatchCard,
  renderAppRecord, rfPass, recFilterBar, socRecordHtml.

## 2026-10-28
- **cmags0511** (PR): Grades everywhere. picks.py: FanDuel's own board (fd_board.json from lab_market.py) is the
  next price fallback after Pinnacle/FanDuel quotes and DraftKings' NBA po/pu (ESPN's NFL feed has no prices), same
  line = real price, a different line = shifted estimate (C at most). index.html: `gradeChip`/`gradeOf` put a grade
  on the All tab, each game's Top 5, the college Top list, soccer Most likely cards (from ev_best) and the Record
  pick log; full cards say "Not graded yet" when no book has posted a price. sw.js bumped.

## 2026-10-28
- **rmolnar10**: Record tab, full pick log: each day's header now shows that day's net units next to its W-L
  (e.g. `3-1 · +1.7u`), green/red/gray, from the same appTally units as the headline (pending picks not counted).
  Display only, no grading change. sw.js pt-v114.

## 2026-10-27
- **cmags0511** (weekly results review, PR): Kalshi disagreement check in `picks.py` (`KALSHI_AGAINST = .49`): when
  Kalshi's traders give the pick's side under 49% at DraftKings' line, the score is halved and the card says so, like
  the sportsbook check (BOOK_GAP). Graded props Oct 8-27: those picks hit 313/716 (44%) vs 54% expected (NBA 41%,
  NFL 48%). Replay of the Top 10 from 401 hourly slate.json versions: -17.2u -> -12.3u (NBA -18.2u -> -13.4u, NFL and
  college unchanged). No front-end change. Also: the Lab market-anchored page (PR #2's idea, live since Oct 20) is
  29-44, -13.1u, so PR #2 isn't supported by results.
- **cmags0511** (PR, on top of #42): Owner's Oct 27 changes. (1) Top lists (picks/byMarket, so the record too) skip
  F grades and prices shorter than -130 (`MIN_PRICE`); game views keep NBA but apply the same filter. (2) NBA Top 10
  paused until Nov 15 (`NBA_TOP_FROM`); NBA lines still on the board. (3) Lab page removed (lab_market.py keeps
  running: it writes fd_board.json, FanDuel's TD prices). (4) RESEARCH.md: news only (flags + sourced facts; side/adj
  +1 only for availability/role facts), no Best bet, no soccer researcher, smaller search budget, college pass 3 =
  news check. (5) Soccer: Team bets is the first/default list; player-prop lists are info only and record.py stops
  recording them after Oct 28 00:00 UTC. (6) TDs: picks.py adds `fd`, `bp` (better of Pinnacle/FanDuel), `td_edge`
  (94% of the chance x payout - 1) and `td_bet` (edge >= -2%); record.py records only `td_bet` TDs, at the better
  price. sw.js pt-v113.
- **cmags0511** (PR): Grades fixed (everything was D). (1) Most NBA picks had no price: picks.py now falls back to
  DraftKings' own po/pu from lines.json when Pinnacle/FanDuel have no quote (also feeds the book-gap and price
  checks in the ranking). (2) Estimated (shifted) prices are graded too, C at most; no price = ungraded. (3) Grade
  model features: under, over, modest app-over-book gap on an under (0-6 pts), big gap (6+ pts, lost in both halves
  of the graded data); out of sample the worst-graded picks returned -9.7%, the rest -3% to 0%. (4) New F grade
  (edge below -2%: avoid). sw.js pt-v112.
- **cmags0511** (PR): Pick grades and suggested units. `picks.py` `grade_model()`/`grade_picks()`: each prop's chance =
  the book's no-vig price (well calibrated on 2,034 graded props with real prices) + learned log-odds adjustments
  for under / over / the app's confidence, refit every run from calib.json with a ridge pull toward the book (first
  fit: under +.10, over -.08, confidence -.02). Edge = chance x payout - 1 → A 5%+ 2u, B 3-5% 1u, C 1-3% 0.5u, D pass;
  no real price = C at most. `parlay` (A/B and 55%+) and `pair` (same-team QB passing + receiver, same side). Ranking
  unchanged. record.py saves grade/units/p_cal/edge; Record tab "By grade" table (W-L, 1u, at suggested stake). Cards
  show the grade line and the graded chance. TD cards graded at FanDuel's price with 94% of the app's chance (TDs ran
  50% predicted / 47% hit); soccer team bets graded from their Pinnacle edge (model-only at half). sw.js pt-v111.
- **cmags0511**: Tested Next Gen Stats as a prop signal (`backtest_ngs.py`, README "Usage signals"): not added. Small
  gains on the synthetic-line backtest didn't hold against real graded DraftKings lines (52-54% at best, some signals
  reversed). No app or model change.

## 2026-10-26
- **rmolnar10**: Walters records audit + star filter (PR). Replayed all 229 hourly walters.json versions (Oct 17–26):
  every kickoff lock matches the last pre-kickoff line/price, every grade matches the final score (checked against
  ESPN), nothing vanished or stuck ungraded, and all 28 early locks since the feature went live (Oct 22 18:13 UTC) match
  the first hour their play showed up. Note: week 8 early locks are from Oct 22, not the true first line (Oct 19).
  `walters.py` now grades only games ESPN marks `completed`, so a postponed/canceled game can't grade 0–0. Walters
  graded picks sheet: a star filter (All / 3 / 2.5 / ... with counts) that shows that tier's rows and record. sw.js pt-v108.
- **rmolnar10**: Walters fixes (PR). `walters.py`: when ESPN drops DraftKings' spread for a while (books pull next
  week's lines during Sunday's games), the game keeps its last line and prices (`lstale: true`) instead of a blank line
  under an old pick ("SEA –"); early locks only take a fresh line. `index.html` Walters page: games after the coming
  Tuesday show their date ("Sun, Nov 1"), so next week's games don't read as this week's; a 3-star game already
  under way shows a Live tag. sw.js pt-v107.
- **cmags0511** (PR): Owner's cleanup after reviewing results. (1) Research leans no longer move picks
  (`RESEARCH_IN_RANKING = False` in picks.py; leans went 74-96): no research term in the chance, no "argued against"
  drop, no unresearched penalty, no research override of the big-gap penalty. Research news still counts (injury /
  ruled out, questionable ×.85, fact-checked line, backup role). Notes still show on cards and research leans are
  still recorded. TD board unchanged (its chances are well calibrated). (2) Best bet off (`BEST_BET_ON = False`;
  3-5). (3) Overs-only switch removed everywhere (`OVERS()` always false, `sideSwitch()` empty; picksOver still
  written but unused). (4) fwarnk removed entirely: fwarnk.py, fwarnk.json, both workflow steps, the page and link.
  Also folds in the soccer Team bets (PR #36). sw.js pt-v110.

## 2026-10-25
- **cmags0511**: Props tab: the separate "Touchdowns" section is gone; the NFL TD lists (Research / Likeliest / Plus
  money, the plus-money pricing box, the live TD tracker) now show under Top picks when the prop type is **Anytime TD**
  (`applySec` sets `data-sec="td"` for that case; a saved `ptSec=td` migrates to picks + td). The "Live anytime TDs"
  placeholder box is hidden until a game is live. sw.js pt-v106.
- **cmags0511**: Touchdowns: new default "Research" list on the NFL Touchdowns section (`tdResearchList`/`renderTdTop`):
  the scorers the research backs (`radj` > 0 in tdAll, plus tdPicks), likeliest first, each with FanDuel's anytime-TD
  odds, the app's chance, fair odds and whether FanDuel pays more or less than fair. FanDuel TD odds come from
  lab_market.py (NFL board now reads the `td-scorer-props` tab; saved as `td` in fd_board.json, never Lab picks);
  the Likeliest / Plus money cards show a "FanDuel" chip too. sw.js pt-v104.

## 2026-10-24
- **cmags0511**: Soccer **Team bets** (third list on the Soccer tab, own record): `soccer_team.py` → `soccer_team.json`,
  new hourly step `soccer_team` in `lines.yml`. Reads Pinnacle's soccer moneyline / every handicap and total line /
  team totals (full match and 1st half, 22 leagues), fits a Dixon-Coles score model to them, and prices every
  FanDuel market settled by the score (result, DNB, double chance, spreads, totals, team totals, BTTS, combos, exact
  goals, margins, goal bands, 1st-half versions) plus DraftKings' moneyline/total from ESPN. Lists bets >=2% over fair
  (markets Pinnacle prices) or >=5% (model-only, max +300), 2 per match, top 25; locks at kickoff, graded from ESPN's
  final / half-time score (summary linescores), cup ties with extra time void. First run: FanDuel averaged 3.5-7%
  under fair on main markets, so few picks. Merged with the Oct 26 cleanup PR.

## 2026-10-22
- **cmags0511**: Soccer: FanDuel's price for each listed pick (`fanduel_prices` in soccer_data.py: FanDuel's public
  soccer page + event tabs, only the matches the lists use; Pinnacle has no soccer player props). Picks carry `fd`,
  `bp`/`bb` (better price and book), `ev_best`; record.py grades soccer at the better price from Oct 23 (`book`, `dk`,
  `fd` saved). Soccer tab reframed: "Most likely" list + a note on the 25-45% cut; cards show both prices. sw.js pt-v103.
- **cmags0511**: Record tab, Soccer: the headline and log count the current lists only (Top picks; Value bets from
  Oct 19 pm). The retired lists (Plus money, Goalscorers, old Best value) keep their rows in socRecordHtml under
  "View all splits and stats". sw.js pt-v102.
- **cmags0511**: Parlay checker at the bottom of My picks (both views): `parlayCheckerHtml`, `pcRun` etc. Saved parlays
  not yet started (+ the slip); each leg's chance (Kalshi, else the app's pick, else hit rate), links between legs in the
  same game (shared games history, shrunk; else pairNote ±.15; opposite sides share one outcome), 20,000 simulated
  slates → each parlay's chance, at least one / all / none, "if A misses, B hits". Front end only. sw.js pt-v101.
- **cmags0511**: "All" in the sport switch (`lg-ALL`, `view-every`, `renderEvery`/`everyTop`): each sport's top 5
  (NFL, NBA, college, soccer Top picks) on one page, same ranking rules, tap → that sport's Top picks. Also: the NBA
  minutes trend now uses this season's games only (from a player's 4th game); it was still mixing in last season.
  sw.js pt-v100.
- **rmolnar10**: Walters 3 star banner copy: "following only the 3 star plays won +221.9u (56%)", bold with a gold
  underline (`.s3em`). sw.js pt-v99.
- **rmolnar10**: Walters "3 star plays only": the gold box (`.s3ban`) now holds the whole section (heading, banner text and
  the plays card); its text styles are scoped to `.s3claim` so the play rows look like everywhere else. The banner's
  "most profitable" copy needs `backtest_book.all3`, which arrives with the first hourly walters run after PR #31.
  sw.js pt-v98.
- **rmolnar10**: Walters 3-star plays get their own row under Locked early on the Walters tab (`s3Row`: this season and
  the backtest) and their own table in the Walters backtest sheet (`seasonTbl`). They're now 3 units each everywhere
  (his sizing, units = stars; was 1u in the 3-star section). `walters.py` writes `backtest_book.all3` / `seasons3`
  (3-star plays at 3u at the closing price: 481-372, +221.9u since 2012). The section is renamed "3 star plays
  only" with a gold banner (`.s3ban`, holding the section's heading and this-season line), a glowing heading (`.s3h`, no pulse under reduced motion) and a gold-ringed card
  (`.s3card`); new `--gold`/`--gold-soft` tokens in both themes. The banner says "most profitable method on this page"
  only while its backtest units beat Walters overall, the Model and weather unders (`s3best`; the text names Walters
  overall only); weather unders return
  slightly more per unit staked (9.1% vs 8.7%), so the claim is about units won. sw.js pt-v97.
- **rmolnar10**: Walters page: the bottom links follow the open tab. Graded picks list only that model's picks; the
  backtest sheet is one table for that model (W-L, win %, units, an All row, its tier/star/wind-rain note) with power
  ratings on the Walters and Model tabs only; How it works shows only that model's sections (`howFor`, `data-t` tags in
  `WAL_HOW`: w/m/x). The ⓘ sheet still has the whole method. Tour step 5 text updated to match. sw.js pt-v95.
- **rmolnar10**: Walters page: (1) tour step 5 "At the bottom" points at the links card (`data-tour="links"`: graded
  picks, backtest by season and power ratings, How it works, About); the ⓘ step mentions replaying the tour. (2)
  `#walters` now stays in the address bar while the page is open, so a bookmark or reload comes back to it (`syncHash`
  at the top of `render()`, enabled by `waltersLink` at boot; other pages drop it; replaceState, so no extra history).
  (3) No auto "Add to Home Screen" tip on the Walters page (the gear menu's Install still shows it). sw.js pt-v94.
- **rmolnar10**: Walters early locks now wait for an hour with a real DraftKings price (walters.py, two conditions), so
  an early pick can't be stuck at an assumed -110. In the history so far, a missing price only happened when DK had the
  line off the board 5-7 days out, never near kickoff. No front-end change.
- **rmolnar10**: Walters tour step 2 is back to its original, more specific text;
  the card still sits below the highlighted section. sw.js pt-v93.
- **rmolnar10**: Walters tour fix: the step card covered the highlighted area on phones when it was tall (tiles + Locked
  early). The tour now scrolls the highlighted area and the card into view together, one above the other, and shortens the highlight when both can't fit
  (`spotH`/`vhNow` in `walTour`, uses visualViewport for Safari's toolbars). Step 2 text shortened. sw.js pt-v92.
- **rmolnar10**: Walters early locks (PR, record logic). `walters.py` now also locks each Walters and Model side play the
  first hour it shows up (`epick`/`eline`/`eprice`/`eunits`/`et`, Walters `eb*` with `ebstars`) and grades it at that
  line and price (`estatus`/`eunits_won`, `ebstatus`/`ebunits_won`), plus `eclv`/`ebclv` = points the line moved its way
  by kickoff. The kickoff record is unchanged and still the main one. Page: a "Locked early" row under the tiles
  (Walters and Model tabs), the early line in each game's Details, and the tour / How it works / About say Walters bet
  as early as he could but our injury and weather sources settle late, so the main record locks at kickoff. Weather
  unders stay kickoff-only. The first early locks are this week's plays at today's lines. sw.js pt-v91.
- **rmolnar10**: Walters tour step 3 "Up and down" (PR): the open tab's backtest total since 2012, a small bar per season
  (units won/lost, `seasonBars`) and the count of winning vs losing seasons with the best and worst year. Reads
  `WAL_BT`, set in `renderWalters` from walters.json, so the numbers follow the data. sw.js pt-v90.
- **rmolnar10**: Walters page (PR, replaces #20): a 4-step tour on the first visit (`walTour`, `WAL_TOUR`, `.wtour`
  CSS, `ptWalTour` in localStorage): the three model tabs, This season vs Backtest, the play rows and Details, and where
  to read more (ⓘ, How it works). Steps point at `data-tour` attributes in `renderWalters`; "Take the page tour" in the
  ⓘ sheet replays it. Also the footer photo is hidden on the Walters page (one line in `render()`). sw.js pt-v89.
- **cmags0511**: NBA form uses this season's games only (owner's call), like college: `nba_early` in picks.py, a player
  needs 3 games this season before his recent results count (form = 0 until then; replaces this morning's 40% scaling).
  Until then the NBA Top 10 is usually empty, and the page explains it (renderTop). sw.js pt-v88.
- **cmags0511**: Pick fixes from the first two weeks of results (owner approved, PR merged):
  - The app opens on Overs + unders (`ptSideV` resets old saved choices once); record.py locks only the full list
    (picks only on the overs list went 16-26, -12.3u; the full list 59-51, -0.3u). The Overs view still works.
  - picks.py `BOOK_GAP` .12 → .05 (Top 10 picks 5-10 points above the book's no-vig hit 35%, 10+ 38%).
  - NBA form counts 40% with no current-season games, +12% a game, full at 5 (opening week 22-26).
  - Low-confidence research no longer moves picks (`CONF["low"] = 0`) and isn't recorded as research picks
    (4-12); low-confidence TD research calls aren't recorded either.
  - TD plus-money list only when Kalshi's chance beats the sportsbook price (was 10-15, -5.8u); often empty.
  sw.js pt-v87.

## 2026-10-20
- **cmags0511**: fwarnk tweaks (only fwarnk files + one line in lab_market.py saving Pinnacle quotes to fd_board.json
  `pin`): NFL now counts only unders on "pricey" teams; overs on "cheap" teams are tracked but don't count; a new
  "NFL unders + Pinnacle" record (same unders, only when Pinnacle leans under at FanDuel's line); teams skipped when a
  key player is on the injury report (NFL receiver 30+ yds, NBA scorer 15+ pts) and NBA second nights of back-to-backs.
  Records are keyed by method. sw.js pt-v86.
- **rmolnar10**: Direct link to the hidden Walters page: `https://cmags0511.github.io/prop-tracker/#walters` opens it
  (`waltersLink` at startup and on hashchange; the hash is removed once open, so a reload goes to the normal app).
  sw.js pt-v84.
- **rmolnar10**: Best bet is now a scratch-off card (`renderBest`, `scratchCard`, `.bbs` CSS). A silver foil covers the
  pick; drag a finger across it (or tap Reveal) and past about half cleared it falls away with a small burst. Once
  revealed it stays revealed on that device for that pick (`ptScratch` in localStorage). The why, sources, "See my
  reasoning" sheet (`reasonHtml`) and + Track show after the reveal; `openSheet` now also gives the Best bet sheet
  "Add to my picks". Same pick and data as before. Light mode comment updated. sw.js pt-v83.
- **rmolnar10**: "Mist" redesign (index.html only, no data or model changes). Dark top nav in both themes; light mode is
  the default (dark only if picked in the new gear menu, which also holds Share/Install). Props: two dropdowns
  (section, prop type) drive the old `#subnav`/`#market` buttons; Top cards open a reasoning sheet (`reasonHtml`,
  `openSheet`) with the numbers, market, factors, splits, matchup, news and game log; phones show 5 picks until "Show
  all 10". Record (`renderAppRecord`): sport tabs, a hero card, Splits and Recent lists; the full stats and full pick log
  open in sheets. The Record tab's log is now all dates expanded inside that sheet, so `dayOpen` is no longer used
  there (My picks keeps it; Lab day rows unchanged). Walters (`renderWalters`): tabs for Walters/Model/Weather, two stat tiles, play
  rows with a Details sheet (`gameSheet`), "No play" list shortened. Poopy / anus hole links and footer photo
  untouched. Tested in Chromium only (Safari not available here). sw.js pt-v82.

## 2026-10-20
- **cmags0511**: fwarnk (owner's request): third hidden page next to "poopy?" / "anus hole" (`view-fw`, `renderFw`).
  `fwarnk.py` → `fwarnk.json`, step `fwarnk` after `lab_market` in both workflows. "The math has to add up": NFL, a
  team's top-4 FanDuel receiving lines / its QB's passing line vs the usual share (learned; .69 to start) → top-2
  receivers over when cheap, under when pricey; NBA, top-6 points lines / team points from FanDuel's total and spread
  (learned; no NBA picks until 10 team-games). `lab_market.py` now saves FanDuel's mapped board plus each game's
  spread/total to `fd_board.json`, so FanDuel is read once an hour for both pages. sw.js pt-v85.

## 2026-10-19
- **cmags0511**: Record tab and My picks pick logs: dates collapse/expand like the Lab's (`dayOpen`, `.dayk`, one
  document-level click handler; two-line edits in renderAppRecord / renderRecord's day rows). rmolnar10: if your Record
  overhaul rewrites those logs, keep `dayOpen` or drop it there. sw.js pt-v81.
- **cmags0511**: Lab pick log: each date collapses/expands (tap the day row; the newest day and days with locked picks
  start open; each day row shows its W-L and units). `S.labOpen`, `.labday`. sw.js pt-v80.
- **cmags0511**: Lab #2 page now runs two methods side by side on FanDuel props, each with its own record: market-anchored
  and "stats only" (the app's own chance vs FanDuel's price, no market check; `picks_stats`/`record_stats` in
  lab_market.json). Comparison table, method switch (`S.labM`) and a "How it works" section (`.labhow`). sw.js pt-v79.
- **cmags0511**: Lab #2 now bets FanDuel's own player props (line and price) for NFL and NBA, from FanDuel's public
  feed (`fd_board` in lab_market.py: NFL passing/receiving/rushing tabs, NBA player-points/-rebounds/-assists/
  -combos/-threes), anchored on Pinnacle moved to FanDuel's line (`fetch_prices.shift`), else Kalshi at the same
  line. App chance from slate.json moved to FanDuel's line. One request per game and tab, hourly.
- **rmolnar10**: Walters page: the top stat strip is now three labeled groups (Walters picks, Model picks, Weather
  unders), each with this season + backtest (`.wtiles` in renderWalters). This week cards now show only Walters plays
  (and weather unders), most stars first, each with a units badge (`.wu`); half stars are a half-filled star icon
  (`starIc`, `.hst`) everywhere on the page. Model picks still count in their record and graded list. sw.js pt-v77.
- **cmags0511**: Lab #2 "anus hole" (owner's request): hidden page next to "poopy?" at the bottom of the Record tab
  (`.secret` row, `view-lab`, `renderLab`). New `lab_market.py` → `lab_market.json`, step `lab_market` after
  record in both workflows: chance anchored on Pinnacle/FanDuel no-vig (Kalshi a quarter, or alone), the app's
  slate p_over at 15-25%, side with better EV at the best real price (anchor book or DraftKings), +2% EV, Top 10,
  locked at kickoff and graded in its own record. Never changes picks.json. `fetch_lines.py` now also saves
  DraftKings' NBA prices from ESPN (`po`/`pu` in lines.json; ESPN lists the over first; NFL items have no prices).
- **cmags0511**: Fix: soccer_data crashed (KeyError 't') on players seen only with a national team; team now comes
  from the match. Soccer had been failing since ~Oct 19 evening.
- **rmolnar10**: Walters weather (PR): new `walters_wx.py` + `walters_wx.json` (Open-Meteo kickoff weather for every
  outdoor game since 2009; walters.py tops it up hourly and lines.yml now commits it). Rain unders (2mm+ forecast,
  backtest 114-74) join the wind unders as "Weather unders"; his rain factor now uses forecast mm instead of
  chance of rain. Snow, wind vs pass rate and QB weather records tested at zero, so they're listed on cards at 0
  points. Guide wording for star sizing fixed (it's per game); How it works spells out each factor's values. sw.js pt-v74.
- **cmags0511**: Audit fixes. Best bet is skipped when the sportsbook's no-vig price or Kalshi gives its side under
  50%, or the line moved against it (`picks.py`, end of main). Anytime-TD research calls that drop off `tdPicks`
  before kickoff (e.g. ruled inactive) are withdrawn from the research record (`record.py` 1d).
- **cmags0511**: Merged (PR #15, owner approved): DraftKings soccer props carry a much bigger margin than assumed,
  so `soccer_data.py` now turns the price into a real chance with a fitted `BOOK_CAL` (replaces `MARGIN`). Soccer
  tab lists are now Top picks (20 likeliest goals/shots/SOT for likely starters, price -250 or longer) and Value
  bets (EV +3%+, capped at +500, no saves/cards); Plus money and Goalscorers retired (still in the record).
  Touches renderSoccer/socCard/socRecordHtml/socFind in index.html and one line in record.py's soccer list loop
  (rmolnar10: your Record overhaul may touch the same record lines). sw.js pt-v73.
- **cmags0511**: Merged (PR #13, owner approved): after Skattebo's 0-carry benching, picks the sportsbook strongly
  disagrees with (model 12+ points above the book's no-vig price: score x .5) or whose DraftKings line moved 12%+
  against them since open (x .6) drop out of the Top lists, and research can't override either. New `book_p`/`open`
  in slate + research packets, RESEARCH.md tells researchers to explain big moves, "Book disagrees" / "Line moved
  against" chips (fxChips). sw.js pt-v72.
- **rmolnar10**: Walters page: "3 models on this page" guide (bottom sheet, `openWalGuide`), green/red This week cards
  with a legend, How it works rewritten as short bullet groups (`WAL_MODELS`/`WAL_HOW` in `renderWalters`). sw.js pt-v71.
- **rmolnar10**: Walters page: "3-star plays" section (Walters picks at 15%+, 1u each, own record + backtest tier). Front end
  only, inside `renderWalters`. sw.js pt-v70.
- **rmolnar10**: Walters page: the book's full method (PR). New `walters_book.py` (his chapter 22 game factors and
  key-number star sizing, computed from the nflverse schedule) used by `walters.py`; each game gets a Walters line,
  its factor list and a star-sized Walters pick, graded alongside the tuned Model picks (`bpick`/`bstars`/`bstatus`
  in walters.json, `backtest_book`). index.html changes are inside `renderWalters` plus `.wfac` styles. sw.js pt-v69.

## 2026-10-18
- **cmags0511**: "Since your last visit" box at the top of Props (Top 10 changes, your picks' injury news and line
  moves, new research; `wcSnap`/`wcDiff`/`renderWhatChanged` in index.html, kept in localStorage `ptSeen`).
  DraftKings line history: new `line_hist.py` → `line_hist.json` (step `line_hist` after fetch_lines in both
  workflows), a "Line moves" tab on each prop and a "DK ▼4 since open" chip on Top picks. College Top 5 box is now a
  Top 10 for the next college game day, filled with labeled leans (`renderCfbTop`). index.html edits are all new
  functions plus small hooks in renderDetail tabs, the Top pick chips, the view-board click handler and boot, so they
  shouldn't collide with the Record tab work. sw.js pt-v68.
- **cmags0511**: Merged (PR #9, owner approved 10/19): weather for more props. Cold for QB and kicker props, a lighter wind
  weight on receiving (`picks.py` COLD_W / WIND_W_REC, `backtest_weather.py`).

## 2026-10-17
- **cmags0511**: Slimmer daily research to stay under the usage limit (RESEARCH.md budget; research_packets.py
  defaults: 3 batches, 60h window, college only within 36h, fact-check 6 calls) + a 10:34 AM backup research run
  that only works when the 7:34 run didn't publish.
- **cmags0511**: A photo (added at the owner's request) at the bottom of every page (`footer.jpg`, `.sitefoot` after `#srcnote` in index.html).
- **rmolnar10**: Walters page: totals (wind unders, 12-19 mph outdoors, backtest 287-212) and non-QB injuries
  listed per game from nflverse snap counts (shown, not weighted: they didn't beat closing lines). PR.
- **rmolnar10**: Walters-style NFL game lines (PR): `walters.py` → `walters.json`, new hourly step `walters`
  in `lines.yml`, hidden page `view-walt` behind the "poopy?" link at the bottom of the Record tab. Data:
  nflverse schedule (games.csv), ESPN scoreboard (DK spread + prices, finals), context.json injuries. Backtest
  440-349 (55.8%) since 2012 vs closing lines at a 4+ point edge.
- **rmolnar10**: Redesign merged (PR #3): Inter type, neutral light/dark palette, bottom tabs Props · Games ·
  My picks · Record (Record = the app's graded Top 10, moved out of My picks), Soccer in the sport switch,
  Props split into Top picks / Touchdowns / Trends / All props. Light/dark switch in the header (PR #4,
  `ptTheme` in localStorage; follows the phone until picked).
- **rmolnar10** — **IN PROGRESS** (touches `index.html`, possibly `record.py`): Record tab overhaul that tracks
  Top 10 and soccer bets at real prices. Note `index.html` changes here so we can fold them in.
- **cmags0511**: slate.json and calib.json now keep each prop's sportsbook prices (`po`/`pu` over/under, `pb` book,
  `pe` estimated) so PR #2 can be judged on real results. PR #2 stays open until ~Oct 27 (two more NFL weekends).
- **cmags0511**: Navigation redesign mockup tried and dropped; the app keeps its current layout. Nothing in
  `index.html` changed, so layout work there is open again.
- **rmolnar10**: Sportsbook prices from Pinnacle and FanDuel (`fetch_prices.py`, step `fetch_prices` in both
  workflows) into `odds.json`; the record grades units at the price saved with each pick (PR #1).
- **cmags0511**: Workflows on checkout v5 / setup-python v6 (Node 24), runner pinned to ubuntu-24.04.
- **cmags0511**: Audit fixes. `build_data.py` writes `box_recent.json` (every NFL player's last 3 weeks, incl.
  snap-only zero lines) and `record.py` grades from it, so picks on fringe players are no longer voided
  (7 past voids re-graded). Soccer team strength now reads ESPN's `moneyline`/`total` blocks. Goalkeeper saves
  lean harder on the book (`MKT_W_M`). Step health files + header warning. Research notes stay usable 72h.
- **cmags0511**: College Top 5 on the CFB board (`renderCfbTop` in index.html).

## 2026-10-15
- **cmags0511**: Usage signals (`build_usage.py`, `usage_lib.py`, `usage.json`): usage projection, snap trend,
  red-zone looks in the TD model, NBA pace. Tested and not used: NFL pace/PROE, opponent missing defenders,
  backup QB, rest.
