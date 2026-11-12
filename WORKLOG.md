# Work log

Newest first. One entry per change: date, who, what, and anything the other person should know.
Mark unfinished work **IN PROGRESS** (with the files it touches) and update the entry when it's done.

## 2026-11-10 (2), rmolnar10 (Claude): Walters data check, stale-lock tracking (PR)
Audit of the Walters page: replayed all 511 walters.json versions (Oct 17 - Nov 10). All 70 NFL games present, no
duplicates, nothing vanished, no graded row or early lock ever changed, every score and grade matches nflverse's finals,
and a fresh run reproduces the ratings and backtests exactly. All 170 players listed out actually didn't play (snap
counts); kickoff wind forecasts land within ~3 mph of the archive. QBs: nflverse's listed starter was right in 11 of 13
QB changes; the 2 misses (TB Oct 25, PHI Oct 27) weren't on any report, so no change.
**Owner, please read:** since ~Nov 6 GitHub has been dropping most scheduled runs (`lines.yml` 3-8 a day instead of
~24, `update.yml` 2-4 instead of 8; every run that starts succeeds). Every hourly lock in the app is affected. On Nov 8
the 1pm NFL games locked lines 3.3 hours old. README "When GitHub skips the scheduled runs" has the fix: an outside
scheduler calling `workflow_dispatch` with a repo-only fine-grained token (needs the owner's account).
Changes: `walters.py` saves `upd` (last fresh line) and, at grading, `lock_h` (hours between that and kickoff). A game
still pending from before ESPN's 4-day window is looked up on its own date, so a long outage can't leave it
ungraded. Walters graded picks show "line Xh old at kickoff" when it's 1.5h+. `walters_lockage.py` is a one-off
that backfills `lock_h` for past games from git history (run once after merge, full clone). No grades changed: the 3
Nov 8 plays whose locked line differed from the close grade the same either way. sw.js pt-v142.

## 2026-11-10, cmags0511 (Claude, weekly results review)
No code change this week: nothing tested cleared the bar. Numbers (units at the saved price, -110 when none; "season" = since prices started Oct 17):
- Top 10: last 7 days 129-100, +12.5u (NBA 82-67 +3.7u, NFL 38-32 +1.7u, college 9-1 +7.2u; all but 3 were unders). Season 254-238, -17.1u (NBA 143-140 -16.5u, NFL 80-73 -2.2u, college 31-25 +1.6u). Real-price picks season 96-96 -17.0u (this week 67-56 +0.5u). NBA pts+ast / PRA / threes in the Top 10 are 29-49 season, but on every graded prop those unders are fine (+6% at real prices), so it's selection noise; tune.py already ranks them lower.
- Since the Nov 6 "locked when found" change: picks the app later dropped went 58-60 -9.8u, picks still listed at kickoff 71-40 +22.3u. Tested "lock only after a pick holds its Top 10 spot for 1-6 hours" on a replay of 791 hourly picks.json versions (graded from calib.json): +22 to +36u better over the season, but it would have cost 6-11u in the latest week, and the replay over-counts picks vs the real record (273 vs 201 since Nov 6). Not proposed; retest next week.
- Calibration (16,751 graded props): NFL 60%+ chances hit 71% this week (n102) but about 55% season (n837, app said ~65%). NFL props with the highest ranking scores (top 300) hit 51% vs 63% claimed: in NFL the score stops sorting winners above ~.12. App minus book no-vig chance: the app's side beats the book's fair chance by 2-4 points on average, about break-even after the margin; BOOK_GAP penalty neutral season-long (5+ pts above the book: NFL -0.1% ROI n617, NBA +0.9% n1934). No change.
- Soccer player Top picks: this week 44-41 -17.4u, season 119-93 -32.6u (the app's own expected profit on them averages -26%). Value list has never had a pick. Replay of 53,709 graded DraftKings soccer props since Oct 18: every slice loses 12-55%, and re-ranking the Top picks by expected profit, a chance floor or a price cap still loses 12-21%. No model change fixes this; owner's call whether these stay counted as bets.
- Research: week 13-16 (props 10-13, TD 3-3); season 111-141 -41.7u (medium 102-124, low 4-12). Leans still only nudge the TD model (small).
- TD bets: season 28-30 -6.0u (likely 17-13, long 8-13); one graded this week (loss).
- Parlays (first week): 52-213 -17.6u. NFL 3-leg 16-96 -29.5u, almost all Nov 8; NBA 3-leg 15-64 +13.5u. Too early: one NFL Sunday, legs shared across many parlays.
- Hidden pages: lab market-anchored week 32-31 +5.8u, season 101-130 -20.7u; stats-only week 31-27 +7.8u, season 112-139 -6.7u. Neither earns a place in the main picks. fwarnk still removed (no file).
- tune.py since Nov 3: form weight .67 -> .61, Kalshi 1.12 -> 1.19, game script 1.08 -> 1.26, NBA PRA/pts+ast trusted less, NFL receptions unders ranked up (x1.25).

## 2026-11-06 (2), cmags0511 (Claude): "Card" tab, every suggested bet by kickoff (PR)
New **Today** button (first shipped as "Card") in the sport bar (`renderToday` in index.html): one list of everything the app suggests now (NFL/NBA/CFB props, anytime TDs, soccer props and team bets, NHL, parlays) from `record.json` pending + `soccer_team.json` + `nhl.json`, sorted by kickoff, with the price to look for, "Bet by" time and the DraftKings button. This device remembers what it has shown (localStorage `pt-card-seen`, try/catch) so a bet the app drops before kickoff shows struck through as "No longer recommended"; entries are purged after kickoff. Nothing is written to My picks. No data files or workflows changed. sw.js `pt-v139`.

## 2026-11-06 (3), cmags0511 (Claude): a suggested bet counts as placed the moment it is found (PR, record logic)
Before: `record.py` deleted any pending prop/TD/soccer/parlay that fell off the app's lists before kickoff, and re-wrote its line and price every run, so a bet you placed could vanish or change. Now (`lock()` and `mark_dropped()` in record.py; same for NHL in nhl_picks.py): the first time a bet is listed it is locked with its **first line, price, odds and `t0` (when found)**; later runs only update `line_now` / `price_now` / `ev_now` (line movement since found); one that falls off the lists before kickoff stays, flagged `dropped` (with when). One entry per bet key, so no duplicates (a side flip does not create a second one). Graded at the first-found price. Still removed: a player ruled out before kickoff (the bet would be void anyway). Not changed: the research Best bet / research calls (analysis records, not bets) and `soccer_team.py` (its `record_all` already keeps every listed bet at its first price; `record` stays "edge still there at kickoff"). Today tab now reads these records: shows Found time, Bet by, line/price movement, and "App dropped it · still counts". Existing pending bets keep their current price as the locked one (history can't be recovered). sw.js `pt-v141`. Replaces the device-only "I bet this" idea (PR #78).

## 2026-11-11, cmags0511 (Claude): parlay cap, max 10 per day (PR, record logic)
Since bets lock when first found (2026-11-06 (3)), the hourly-regenerating parlay list piled up in record.json (55 upcoming, 40 already dropped by the app, vs 15 on the Parlays page). `record.py` 1g now keeps at most `PARLAY_DAY_CAP = 10` parlays per ET kickoff day: new parlays take open slots best-EV first, the rest still show on the Parlays page but are not tracked; if a day is already over the cap, the lowest-EV parlays the app has already dropped are deleted (never one still on the board). Chosen by the owner (options were 3 per game, hold 3 hours, 10 per day). Props are unchanged.

## 2026-11-11 (2), cmags0511 (Claude): parlay rules and NBA per-game cap (PR, model/record logic)
Owner's rules: (1) **Parlays, NFL and NBA the same:** built on game days only (a sport's games played today, ET; `parlays.py` filters legs to today), at most ONE same-game parlay per game (the best, `SGP_PER_GAME`), plus up to 5 cross-game parlays per sport (`KEEP`). (2) `record.py` parlay cap is now `PARLAY_DAY_CAP = 20` per sport per day (was 10 per day, PR #81) so a 13-game Sunday can track one SGP per game. (3) **NBA props:** at most 2 picks per game in the Top 10, on the page (`PG_CAP`/`pgFull` in index.html, 3 Top-list sites) and in the record (`PER_GAME_CAP` in record.py), same rule in both. Checked on a data copy: simulated NFL Sunday gives 5 SGP (one per game) + 5 cross; NBA Top 10 has max 2 per game. sw.js `pt-v142`.
Soccer finding (no change made yet): all 212 graded soccer picks were on the model-ranked "Top" list at prices of -150 to -299; they hit 56% but the book prices implied 66% (model said 50%, every one had negative EV). The -200 to -299 bucket is 75-63 for -29.9 units; -199 and shorter is about break-even. Proposal: raise `TOP_MIN_PRICE` in soccer_data.py from -250 to -200.

## 2026-11-11 (4), cmags0511 (Claude): NBA prop-type/side multipliers now come from calib.json, not the Top 10 (PR, model weights)
Audit on calib.json (8.5k graded NBA props with the book's no-vig chance, Oct 20 - Nov 11): the stats model's accuracy equals the market's (log loss .6886 vs .6883 vs Pinnacle; a 50/50 blend is best, .6874), its confidence gap adds nothing (flat across terciles), but **unders beat the market by +3.9% (ROI +1.0% at the book price) and overs lose (-1.1%, ROI -8%)**, strongest in PRA / PA / PR unders (+6 / +6 / +5% edge, ROI +5 to +7%, positive in each of the 4 weeks). The old `tune.py` per-market multiplier used the record's Top 10 (n>=8 per group) and the multiplier itself decides what reaches the Top 10, so it had cut NBA PA unders x0.68, PRA x0.83 and 3PM x0.71, the groups that win. Now NBA multipliers use calib.json: edge = hit rate minus no-vig chance, shrunk by n/(n+300), min 150 props, x(1+3*edge) clamped .6-1.25. Test on a data copy: NBA Top picks move from PR/PTS unders to PRA/PR/PA unders. NFL/CFB multipliers unchanged (still from the Top 10). Honest caveats: only 3 weeks of data; effects are correlated within games; the record's own PA/PRA picks went 8-17 / 11-16 (small, one bad slate). Watch the NBA record. An earlier check I made ("95% of picks negative EV vs the sharp price") was an artifact (same book's vig), discarded.

## 2026-11-06, cmags0511 (Claude): parlay record shows what is locked, by day (PR)
Parlay record screen (`parRecordHtml`): "pending" is now "locked", and one line under the summary says how many are locked per game day and that only the app's suggested parlays count. No data or grading change. `sw.js` is `pt-v138`.

## 2026-11-04 (3), cmags0511 (Claude): soccer team bets, no duplicate rows (PR)
`soccer_team.py`: the same bet at both books (Mainz v Bayern Draw at DraftKings and FanDuel, both +500) showed twice: the book that lost the tie went to the "lapsed" list and into the "all listed" record. Now a bet is identified by game + market + period + side (`bet_sig`): an old pick whose bet is already listed at the other book isn't kept as lapsed, and pending "all listed" rows for the same bet are cut to one (the better price). Graded rows are never touched. The data files were not hand-edited; the next run cleans them up.

## 2026-11-04 (2), cmags0511 (Claude): DraftKings button is now a real link (PR)
The first version was a button that called `window.open`; on the owner's phone it didn't open DraftKings and the card's own sheet opened instead. `dkBtn()` now renders an `<a target="_blank">` (phones open links and hand them to the DraftKings app); the tap handler sets the game's URL, copies the bet text and stops the card underneath from reacting. Tested headless (new tab opens the game page, no sheet). `sw.js` is `pt-v137`. Not tested on a real phone.

## 2026-11-04, cmags0511 (Claude): "DraftKings" button on every bet (PR)
`fetch_dklinks.py` -> `dklinks.json` (hourly in `lines.yml`, and `update.yml`): ESPN's free scoreboard odds carry DraftKings' own game links; the DraftKings event ID inside becomes `sportsbook.draftkings.com/event/<id>`. `index.html` `dkBtn()` puts a "DraftKings ↗" button on the Top pick and Best bet cards, soccer and NHL cards and every parlay leg: it opens the game's DraftKings page (home page if the game isn't listed) and copies the bet's text ("Jahan Dotson under 26.5 receiving yards") to search for. No link to the single prop: that needs The Odds API's per-bet links (checked with one credit: DraftKings returns them, e.g. `/?outcomes=...`), which cost credits, so they are not used. `sw.js` is `pt-v135`. Also on the NHL game list rows. Not yet: the game drawer and My picks rows. NHL: ESPN lists DraftKings pages for only some games.

## 2026-11-03 (5), cmags0511 (Claude): NFL parlays can use near-fair partner legs (PR)
`picks.py`: `legs` now also carries NFL props with a real price and an edge of -3% or better that aren't graded C, flagged `partner`. `parlays.py`: up to 20 partners join the pool but only count in a parlay if a same-game pair with another leg lifts the chance by 3%+ (a pass-heavy script, QB and his receiver), and at least one leg must be a normal edge leg. NFL leg chances are pulled to 50% harder (`SHRINK_LG` .85 vs .95) because the app's NFL 60%+ chances have run too high. The note on a pair with no measured link now says "no clear link" instead of "pull apart". No front-end change. Overs can be partners down to -8% edge (books shade them) but only if a same-game pair with an UNDER leg lifts the parlay's chance (`OVER_PARTNERS` 15). Checked with a synthetic Young passing-yards over: his history says it doesn't pair with Hubbard's rushing under (corr ~0) and works against the receiver unders, so no mix formed, which is the intended behaviour. On the Tuesday test no NFL over had a price yet (only unders), so no over/under mixes showed; expect them when a full Sunday slate is priced. Nothing NFL has been graded in the parlay record yet.

## 2026-11-03 (4), cmags0511 (Claude): NHL "Most likely" now ranks by price (PR)
`nhl_picks.py`: the top list takes bets with a 55%+ chance and ranks by expected profit instead of by chance alone (it was all -230/-250 favourites). `index.html` renamed it "Best-priced likely bets"; `sw.js` is `pt-v134`. Today's list is all shots-on-goal unders, which is where the two-way prices are measured rather than assumed; watch whether the record backs that up (the model may lean under). Old locked picks keep their old list label.

## 2026-11-03 (3), cmags0511 (Claude): NHL tab (PR)
New NHL section, formatted like Soccer: Top picks (Most likely, Value bets), Games (every priced player bet), and its own record.
- `nhl_data.py`: ESPN box-score crawler -> `nhl_hist.json.gz` (skater TOI/goals/assists/shots, goalie shots faced, team shots). Newest first, 350 new games per run, back to Oct 2025. Runs in `update.yml` only (so the two workflows never both rewrite the history).
- `nhl_model.py` + `nhl_backtest.py`: stats model (weighted recent rates shrunk toward position, opponent shots/goals allowed, Poisson / negative binomial). Backtested on regular-season days: chances are calibrated and beat a base rate (log loss .558 vs .611), but there are no historical prices, so this does NOT show an edge over the book. Goalie saves barely beat a base rate.
- `nhl_picks.py` -> `nhl.json` (hourly in `lines.yml`, and in `update.yml`): FanDuel's public NHL markets (shots on goal over/under, anytime goal scorer, 1+/2+ points, 1+/2+ assists), margin removed (two-way where it exists, an assumed margin for yes-only prices), blended 65% market / 35% model. Top picks and Value bets lock at puck drop and are graded from the box scores (units at the FanDuel price). Prices are FanDuel's, labelled "check DraftKings". Goalie saves are not listed: FanDuel's feed has no saves market.
- Front end: NHL button + `renderNhl()` in `index.html`; `sw.js` is `pt-v133`. Not yet: tracking NHL picks into My picks, DraftKings quotes, NHL in the Record tab (the record is on the NHL tab).
- Fixed on the way: the crawler used to save the oldest game's team for a player; `nhl_model.Hist` now takes it from the latest game.

## 2026-11-03 (2), cmags0511 (Claude, weekly results review)
No code change this week: none of the fixes tested held up. Numbers (record.json / calib.json, units at the saved price, -110 when none):
- Top 10: last 7 days 10-18, -8.7u (all NFL/college, 27 of 28 unders, 9 with no price; sacks 0-3); season (since Oct 17) 115-126, -26.2u (NBA 51-61 -16.8u, NFL 42-41 -3.9u, college 22-24 -5.5u). Picks with a real book price went 21-33 while the book's no-vig chance expected about 29 wins.
- Calibration (11,190 graded props): the app's chance is fine up to 60%, overconfident above it. NFL props it gave 60%+ hit 53.5% (n=731, app said 66%); at real prices they returned -12% to -40%, in both halves of the season. tune.py already shrinks confidence (b=.35), and the last 7 days are closer (60-65%: 56.7% hit).
- Tested on a replay of the Top 10 from 667 hourly slate.json versions (Oct 16 - Nov 3), graded from calib.json; replay of today's rules: 131-129, -10.6u.
  (1) Skip picks with the app's chance 60%+: +12.3u. Rejected: in the real record those picks were 41-32, +3.7u (the losers were the under-60% ones, 74-94, -29.9u), so the gain is from different replacement picks, and a 62% cut gives only -1.9u.
  (2) Top 10 only grade C or better: +9.9u, but not stable by threshold (edge >= .005 +3.8u, >= .015 -0.2u, >= .03 -1.2u), and on all priced props a walk-forward grade edge doesn't sort profit (C/B 1-3%: +0.6%, A 3%+: -7.0%).
  (3) Real prices only: +8.3u in the replay, but the real record's real-price picks were the worse half (21-33). Not proposed.
- Research: 60-83 (props 51-69, TD 9-14); medium confidence 56-76. Leans already don't move picks.
- TD (td_bet only since Oct 27): season 15-16, -3.8u; one graded pick last week (won, +2.2u).
- Soccer player Top picks ("Most likely"): 75-52 but -15.2u (FanDuel's prices imply 68%, they hit 59%; the app's own EV already marks most of them negative). Value list: no picks recorded. Team bets (soccer_team.json): 18-36, +16.5u in their first week, longshots, too early to judge.
- Lab market-anchored: 58-87, -24.8u; stats-only: 74-104, -15.2u. Neither earns a place in the main picks. fwarnk was removed Oct 26 (no data).

## 2026-11-03 (2), cmags0511 (Claude)
Soccer team bets: second record, "everything listed" (`soccer_team.json` `record_all`, soccer_team.py main(); index.html `socAllListedHtml`, sw.js v132). Owner wanted lapsed bets (listed, then lost their edge before kickoff) counted somewhere without touching the main record. The main team-bet `record` and everything in record.json are unchanged. `record_all` holds every team bet the page showed before kickoff, lapsed ones included, at the price it was FIRST listed at, locked at kickoff and graded the same way. It's seeded from the existing record, so it starts equal to it and only diverges as new bets lapse (bets that lapsed before today weren't saved). Shown in Record > Soccer ("Team bets: two ways to count") and as a short "all listed" figure on the Soccer tab's record line when the two differ.

## 2026-11-03, cmags0511 (Claude)
**Best parlays** (NFL + NBA), new `parlays.py` -> `parlays.json`, own record. Owner asked for parlays built from the ranked props. Honest framing (also on the page): a parlay's expected profit is the product of each leg's chance x price, so a leg that is a bad price alone is still a bad price inside a parlay; the only real edge is correlation between players in the same game. So:
- picks.py now writes `legs` into picks.json: upcoming NFL/NBA props graded C or better at a real (non-estimated) quote.
- parlays.py combines 2-3 legs (one per player, same ET day), chance = product of leg chances (each pulled 5% toward 50%) times a pair factor for same-game pairs (empirical co-hit rate from shared games in props_data.json, blended with a small football prior; needs 8+ shared games to count). Price = product of leg prices, minus half the correlation boost for same-game legs (DraftKings prices SGPs with correlation). Keeps combos with EV >= 3% (2 legs) / 4% (3 legs). Shows the "worth it at +X or better" fair price.
- record.py section 1g: locks the board's parlays until the first leg kicks off, grades leg by leg (loss if any leg loses, push/void legs drop out), `record.json` "parlays". Units are 1u at the estimated price, so they're approximate. Shown under Record > Parlays (own tab), not mixed into the Top 10 record.
- index.html: "Best parlays" under the Top picks list (NFL/NBA, "Best overall" view), "+ Add to parlay" puts the legs on the parlay slip. sw.js v131. New workflow step `parlays` in lines.yml and update.yml (before record); parlays.json is committed with the other data.
- Untested on real slates (only C-grade legs exist off-day); first NFL Sunday will show how many parlays survive the EV filter. Not backtested: no historical parlay prices exist.

## 2026-11-02 (6), cmags0511 (Claude)
Games tab: anytime TDs can be tracked. Real cause of "can't track anytime TDs": the expanded player card (renderDetail) skipped the Track bar for every fixed-line market (`m.fixed?"":...`), so a TD row opened from a game showed the price and chart but no button. Now a TD gets one "+ Track anytime TD" button (Over 0.5; straight or parlay via chooseTrack). index.html, sw.js v130. The Top picks TD cards already tracked fine (PR #65 only added a fallback there).

## 2026-11-02 (5), cmags0511 (Claude)
Anytime-TD "+ Track" hardening (index.html, sw.js v129). Owner reported he couldn't track anytime TDs; I couldn't reproduce it (every TD card on all three lists tracks, real taps and simulated clocks tried). The tap used to do nothing, silently, if the card's key wasn't found in the picks lists. Now a TD key (`lg|id|td`) that isn't found is rebuilt from the player's next game (over 0.5), and any other miss shows a "Couldn't track that pick" toast instead of nothing.

## 2026-11-02 (4), cmags0511 (Claude)
DraftKings' own price on every pick (owner bets only at DraftKings). picks.py keeps ESPN's DraftKings line and price for the pick's side as `dk_line` / `dk_price` (taken before another book's quote replaces
them). The Top picks cards show "DK -115" under the price when the grade was worked out at Pinnacle's or FanDuel's price (red when DraftKings pays less, "DK no price" when ESPN's feed has none), and
the reasoning sheet has a "Your book" note saying whether DraftKings pays more or less than the price the grade used, or whether its line differs. sw.js v128. The grade itself is unchanged (still Pinnacle,
else FanDuel, else DraftKings' own price): switching it to DraftKings-only would change the grades and the record, so that needs the owner's say-so.

## 2026-11-02 (3), cmags0511 (Claude)
Owner's call: NBA Top 10 is back on (picks.py `NBA_TOP_FROM` moved from Nov 15 to Nov 2; it was paused Oct 27 after NBA went 46%, -12.7u with 4-6 games per player). NBA picks are recorded again from the next lock;
the record will show them plainly. Also a collapsible "How to read a pick" box under the heading on the Top picks page (open on Best overall), sw.js v127: grade = strength, the % is the app's chance, real vs assumed/≈ price,
what the Research labels mean, order is ranking not strength, plus the grade key. Today's ranking run: A 0, B 4, C 251, D 428, F 70 (so C or better is not rare right now; this is mostly NBA unders).

## 2026-11-02 (2), cmags0511 (Claude)
Soccer team bets no longer vanish (soccer_team.py, index.html, sw.js v126). The list was rebuilt every run from bets that beat Pinnacle's fair price right now, so a bet someone already
placed dropped off as soon as FanDuel's price or Pinnacle's fair price moved. Now a listed bet that stops qualifying stays on the list until kickoff, marked `lapsed` ("no longer an edge" on the card,
with the price it was listed at and today's price, or "off the board"), ranked last and without a grade. It keeps its original price on later runs. The record is unchanged: it counts only bets still
listed at kickoff (lapsed ones are not recorded, same as before). If you want lapsed bets counted too, that's a record-logic change (PR first).

## 2026-11-02, cmags0511 (Claude)
Record tab (index.html, sw.js v125): the pick log now groups each day's picks under kickoff headers ("NFL · 4:25 PM kickoff · 6 picks"), and the note says the Top 10 refills as
games start so a busy day can lock more than 10 picks for a sport. Display only: record.py and record.json are unchanged (the record is still every Top 10 pick as it stood before its game).
Why: users saw more bets in the record than in the Top 10 on the Props tab.

## 2026-10-31 (2), cmags0511 (Claude)
Fix (index.html, sw.js v124): college props the books don't post. (1) The estimated-line props for college skipped the position filter (`lg!=="NFL"||m.pos.includes`), so any college RB or WR who
had thrown a pass got a "passing yards" prop; the position filter now applies to college too (NBA still has none). (2) `MK.CFB` no longer has Rush + Rec yards (college books don't post it; the
NFL list had been reused). NFL is unchanged.

## 2026-10-31, cmags0511 (Claude)
Fix: college props still showed no prices on game day. Diagnostic (OddsPapi, NU/ORE and OU/SC): DraftKings posts college carries and pass completions only as one-sided "k+" ladders
(Over price per rung, no Under), so `fetch_oddspapi.py`, which needed both sides, dropped them. It now reads an Over-only ladder with `fetch_prices.ladder()` (the same method as the
kicking-points ladders): the Over at the app's line comes from the rung (or between rungs), the Under is estimated (`est_under`, so graded C at most). picks.py passes the est flags
through. `tried` keys got a `v2` prefix so the games tried before the fix are asked again. Props nobody lists at all (some receptions / receiving yards for fringe players) stay unpriced.

## 2026-10-30 (6), cmags0511 (Claude)
Fix: the first live run of the Odds API and OddsPapi fallbacks couldn't match any college game ("no single matching event" / "0 matching fixtures"): ESPN's college
abbreviations aren't letter patterns of the school names (NU is Northwestern, OU and PSU have no matching letters). New `cfb_teams.json` (ESPN abbreviation -> name,
built by `build_cfb_teams.py`, FBS first so OSU is Ohio State) and `fetch_odds.cfb_fits()` used by both fetchers; letter matching stays as the fallback for a team not in the table.

## 2026-10-30 (5), cmags0511 (Claude)
OddsPapi (free plan, 250 requests a month, `ODDSPAPI_KEY` secret) as a second last-resort price, after The Odds API and before SportsGameOdds. Probe (Oct 30): the free key
returns real DraftKings, FanDuel, BetMGM and Pinnacle quotes for college and NFL player props (pass yards/attempts/completions, rush yards/attempts, receptions, receiving
yards, rush+rec, kicker props, sacks, tackles+assists), one request per GAME for every market, so it is far cheaper than per-market credits. `fetch_oddspapi.py` (new step
`fetch_oddspapi` in lines.yml, then picks.py again) asks only about games in the next 30 hours with 2+ props still unpriced, at most 10 games a run, never the same game
again for 12 hours, and keeps 4 requests a day in reserve; usage is stored in `oddspapi_prices.json`. `oddspapi_markets.json` is a small table of OddsPapi market ids
(type, line, Over/Under outcome ids) built from its 19 MB catalogue with `python fetch_oddspapi.py --markets` (refresh monthly). Output is `oddspapi_prices.json` (not
`oddsapi.json`, which is The Odds API). Untested live end to end: the first college Saturday run will show how many props get filled (check `log` and `usage`). Not
touched: NBA (small gaps; The Odds API and SportsGameOdds cover it).

## 2026-10-30 (4), cmags0511 (Claude)
The Odds API (free plan, 500 credits a month, `ODDS_API_KEY` secret) is now a last-resort price too, not a top-picks price. `fetch_odds.py` was rewritten: it reads
slate.json and asks only for props with no price from Pinnacle, FanDuel or ESPN's feed (and a score of at least .12), in games starting within 28 hours, one request
per game with only the prop types that game needs (1 credit each). Best games first, at most 30 credits a run, never the same game and prop types again for 12 hours,
and it keeps 10 credits a day for the rest of the month. It now also covers college football (`americanfootball_ncaaf`; teams matched by kickoff time plus
abbreviation letters, skipped when not exactly one event fits). Output moved from `odds.json` to its own `oddsapi.json` (fetch_prices rewrites odds.json every run, which would have wiped it); picks.py
uses it right after the DraftKings-feed price and before SportsGameOdds. Untested against the live API: the first college Saturday run will show how many props
get filled (check `oddsapi.json` `log` and `remaining`).

## 2026-10-30 (3), cmags0511 (Claude)
SportsGameOdds (free plan, `SGO_API_KEY` secret) as the last-resort price. Probe (Oct 30): the free plan returns real DraftKings, FanDuel, Caesars, BetMGM, ESPN BET
and Bovada player-prop prices for NFL, college and NBA, but no tackles or sacks (those stay at the flagged -110). `fetch_sgo.py` (new step `fetch_sgo` in
lines.yml, then picks.py again) prices ONLY props that have no price from Pinnacle, FanDuel, ESPN's feed or The Odds API, at the app's line (a different line
is moved to it with fetch_prices.shift and marked estimated). It reads slate.json for what is unpriced, asks only for games in the next 30 hours that have
4+ unpriced props, refetches a league at most every 6 hours (24 if the last fetch priced under 10%), and stops at 2,200 of the 2,500 monthly objects, paced over
the month. Real test: NBA priced 27 of 30 unpriced props for 22 objects; college priced 0 of 36 (the free plan lists about 41 college players across 11 games and
none were ours; the unpriced college props are mostly minor ones the books don't post). NFL untested until a game day (kicking props: pat, fgm, kpts).
Name matching is fuzzy (alex sarr ~ alexandre sarr). `sgo.json` keeps the last run's log (`log`), usage and per-league fill rate. `sgo_probe.py` is on branch
sgo-probe (not merged).

## 2026-10-30 (2), cmags0511 (Claude)
College blowout factor. `picks.py`: new `blowout` part for CFB passing/rushing/receiving volume props (`BLOW_M`): up to -0.45 log-odds on the over
(so toward the under) as the spread grows from 10 to 24+, at less than half the size the Oct 30 backtest found (the real line already shades for
blowouts). `tune.py` learns its weight from graded picks once 60+ carry it; `index.html` labels the chip "Blowout" (`sw.js` pt-v123). On today's slate only
2 of 34 college candidates are in games with a spread over 10, so almost nothing moves yet (Stockton under 238.5 .149 -> .174); it matters on lopsided
slates. Team pass rate (also significant in the backtest) is not used: it overlaps with the player's own attempt history.

## 2026-10-30, cmags0511 (Claude, research run)
`merge_notes.py`: anytime-TD notes are also accepted for keys on the app's Top anytime-TD list (`picks.json` tdTop), not only packet `td_candidates`. Games without a packet (this week LAR) had their audit fix notes dropped as unknown keys. No ranking change.

## 2026-10-30, cmags0511 (Claude)
Backtests of new factors (Oct 30). Pinnacle's no-vig probability vs the app's model on 3,415 graded NBA/NFL props with a Pinnacle price (calib.json):
Pinnacle was the better predictor (log-loss NBA .6878 vs .6918, NFL .6859 vs .7021); stacked, the model's weight was -0.54 vs +1.10 for Pinnacle;
walk-forward gain +.0048 log-loss (day-bootstrap 90% range +.0023 to +.0071, 10 days). Top 20% by the blend hit 59.4% vs 52.1% but ROI at
Pinnacle's price was about the same (-2.4% vs -2.5%): more hits, no more profit. None of the app's own factors (form, matchup, game, usage, Kalshi,
minutes, news) added anything on top of Pinnacle's probability; NBA matchup made it worse (t -3.6). Nothing in picks.py changed.
Soccer lineups: all 78 graded player picks were starters, so a lineup check would have changed nothing.
College (`backtest_cfb.py`, run by the manual "CFB backtest" workflow with the `CFBD_API_KEY` secret; results in `backtest_results/cfb.txt`):
23 of 84 feature tests beat the base with t >= 2 (about 2 expected by chance). Strongest are the point spread / blowout size (attempts, carries,
yards), team pass rate (attempts, completions) and last year's SP+ ratings (rushing yards). In games with a spread of 14+ either way, overs on the
synthetic (last-10 average) line hit 26-49% for yardage and attempts. Caveat: the test line is a player's own average, not a sportsbook line, and
real lines already shade for blowouts, so this isn't proof of an edge against DraftKings; it applies directly to college "leans vs his typical game".
`record.py` now also stores ESPN's opening line (`open`) on each calib.json row, so line movement can be backtested after a few weeks of games.

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
- 2026-11-08 **cmags0511 (scheduled inactives check, 1 PM games)**: added availability notes for 7 unresearched Top 10 / Top TD picks (Goff, Javonte Williams, B. Stephens, Sutton, J. Taylor, Nacua, I. Likely); none ruled out. Pickens/Ferguson still questionable, inactives not yet posted at check time.
- 2026-11-08 **cmags0511 (scheduled inactives check, late games)**: notes for 7 unresearched Top 10 / Top TD picks (McCaffrey rry, Q. Walker, Crosby, Schultz, Buzelis, Jacobs TD, Smith-Njigba TD); none ruled out. JSN TD flagged caution (Darnold out, Lock questionable). Stevenson rush-yds note set to adj 0 (Henderson news already in the line).
- 2026-11-08 **cmags0511 (scheduled evening news check)**: Monangai ruled out for SNF (TD note flag out); Swift TD upgraded to support +1; R. Johnson caution cleared. Added availability notes for 13 unresearched Top 10 picks (none out); Kuzma 3PM line drop 1.5→0.5 still unexplained. SNF inactives not yet posted at check time.
- 2026-11-08 **cmags0511 (scheduled inactives check, SNF + night NBA)**: notes for 6 unresearched Top 10 picks (Loveland, A. Bailey, Adebayo, K. George, K. Dunn, Hachimura); none ruled out. George (illness) upgraded to available; Markkanen questionable. SNF official inactives not yet posted at check time.
- 2026-11-09 **cmags0511 (scheduled research check, AM)**: 8 games (MNF BUF@MIN + 7 NBA). Murray out/Wentz starts, Jennings out, Dawkins/Anderson questionable; Doncic out, A. Davis and Vassell questionable. Mason TD note cut to adj 0 after fact-check. No MAC props posted yet. Naz Reid pts+reb under still conflicts with the usage-over note.
- 2026-11-09 **cmags0511 (scheduled evening news check)**: Reaves (illness) questionable → all Reaves notes set to caution (over leans removed); reports conflict on Doncic (back). Jokic questionable → caution. Availability notes for 6 unresearched Top 10 picks (Harden, Walter, A. Thompson, Nesmith, Wembanyama, Cunningham); none out. MNF: Dawkins/Anderson still questionable, inactives not posted at check time.
- 2026-11-10 **cmags0511 (scheduled research check, AM)**: 4 NBA games + 6 MAC games. Utah without K. George/JJJ/Nurkic, Markkanen questionable (caution); D. Peterson over +1. Hart questionable; R. Williams III cleared. Larsson start not confirmed for tonight (adj 0); app 3PM lines for Larsson (books 1.5) and Adebayo (books split 0.5/1.5) lag. 5 MAC lines only; Luster pyd unresearched. NFL Sunday TD/Top 10 picks left for later runs (>60h).
- 2026-11-10 **cmags0511 (scheduled evening news check)**: 6 NBA games tonight. Markkanen ruled out (flag out); Josh Green start confirmed (over +1); Hart downgraded to doubtful (Shamet caution cleared); Sabonis questionable, K. Murray cleared; Herro/Ware questionable for MIL. Availability notes for 20 unresearched Top 10 picks, none out. D. Peterson reb+ast under still conflicts with the George/Markkanen-out over note (left as is).
- 2026-11-11 **cmags0511 (scheduled research check, AM)**: TNF WAS@NYG + 3 NBA + 3 MAC + 6 Nations League players. Skattebo full practice, expected back (Singletary notes under/caution); Croskey-Merritt (IR) out. TOR without Barnes/Leonard, Quickley questionable; Powell (now back spasms), Vassell, McConnell questionable. Only 2 MAC lines found (Luster, Richter). Walter pr / Barrett pra unders still conflict with the Barnes-out over notes (left as is). Sunday NFL left for later runs.
- 2026-11-12 **cmags0511 (scheduled research check, AM)**: TNF WAS@NYG, DET@WSH + quality-gate checks on 6 NBA games, 3 college games (21 lines), 14 Nations League players. Skattebo expected back (Singletary notes caution, adj 0 after fact-check: final status unconfirmed); Embiid questionable (caution); MIN without Edwards/DiVincenzo; Heintschel out, Geriner starts for Pitt Fri. No current posted lines found for any target (line checks came up empty).
