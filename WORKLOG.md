# Work log

Newest first. One entry per change: date, who, what, and anything the other person should know.
Mark unfinished work **IN PROGRESS** (with the files it touches) and update the entry when it's done.

## 2026-10-22
- **rmolnar10**: Walters 3-star plays get their own row under Locked early on the Walters tab (`s3Row`: this season and
  the backtest) and their own table in the Walters backtest sheet (`seasonTbl`). They're now 3 units each everywhere
  (his sizing, units = stars; was 1u in the 3-star section). `walters.py` writes `backtest_book.all3` / `seasons3`
  (3-star plays at 3u at the closing price: 481-372, +221.9u since 2012). sw.js pt-v96.
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
