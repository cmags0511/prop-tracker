# Research playbook (the research check)

The app's numbers already cover recent form, the opponent's defense against his position, the game's
spread and total, minutes trends, the ESPN injury report and depth chart, kickoff wind and the Kalshi
market price. **Your job is what the numbers can't see**, for the props people actually look at.

The owner prefers **overs**; the app shows overs by default. Spend most of the effort on overs, but be
honest: if the research says under, say under.

**Budget.** Research runs once a day in full (7:34 AM ET) plus quick news checks, on the owner's Claude usage, and an earlier version that researched every
prop in every game used it all up. Stay inside these limits: at most 4 NFL/NBA researchers plus 1
college researcher and 1 fact-checker, about 4 searches per game for the game-level picture plus 1-2 per target prop
(the college researcher gets about 25),
and open only the articles that matter. Quality over volume: a few specific, sourced findings beat
seven vague angles.

## Steps

1. **Get the repo.** `add_repo` (owner `cmags0511`, repo `prop-tracker`, access `push`), then
   `git clone --depth 1 https://github.com/cmags0511/prop-tracker` and work inside it.
2. **Learn from the record.** `record.json` → `"research"` holds every past research call graded
   win/loss/push, with its `adj`, `conf`, `side` and the stats `lean`. Tally the graded ones by
   confidence, by strength and by "research went against the stats". Put 2-3 lessons in each brief you
   hand out (for example "low-confidence calls are 4-9: only make them when the news is concrete" or
   "calls against the stats are losing: need two sources to go against the numbers"). Skip this when
   fewer than 20 calls are graded.
3. **Build the packets.** `python research_packets.py`. It prints up to 4 batches of games
   (`research/batches/batch-<n>.json`, each a list of packet ids) and, when college games are within
   60 hours, `CFB-week`. Each game packet (`research/packets/<id>.json`) has the spread/total, weather,
   both injury reports with practice notes, starters, its `targets` (the props the app shows: Top 10s,
   game Top 5s, Kalshi gaps, teammate-out bumps, each with `why_target`) and up to 8 `other_props`.
4. **Start the researchers, all in one message (Agent tool), so they run in parallel:** one per batch
   with the "Game researcher brief", plus one with the "College researcher brief" if `CFB-week` exists.
   If the Agent tool isn't available, do the batches yourself, soonest games first.
5. **Check the write-ups** in `research/out/`. If one is missing or empty, publish without it (don't
   rerun it). Don't send researchers back for more unless a target in a `full` game is missing entirely.
6. **Fact-check the strongest calls.** Collect the 10 calls that will matter most: every note with
   adj +2 or conf high, the `best_candidate`s and the anytime-TD notes. Start ONE fact-checker (Agent
   tool) with that list (key, player, side, note, sources). For each call it identifies the one or two
   facts the call rests on (he's starting, he practiced fully, the defender is out, his snap share) and
   verifies them with one fresh search each, preferring official team sources and the latest reports.
   It also checks the LINE for each of these calls and for every pick in the current overs Top 10
   (`python audit_top.py` lists them): one current odds page per player (BettingPros prop pages show the
   consensus and each book; Covers, Action Network or the book's own research pages also work). Where
   the posted line differs from the app's, add `"line_now": <number>, "line_src": "<url>"` to that note.
   It returns, per call, `confirmed`, `weakened` (with the corrected fact) or `wrong`. Apply the results
   in `research/out/` before merging: `weakened` → lower `adj` by 1 and `conf` to medium and fix the
   wording; `wrong` → set `adj` to 0, `flag` to `caution` (or `out` if he's not playing) and rewrite the
   note with the corrected fact. Never make the Best bet from a call that wasn't `confirmed`.
7. **Choose the Best bet** from the researchers' `best_candidate`s: the single OVER where stats, matchup,
   role, conditions, market and news line up best (an under only if no over is sound). He must be a
   confirmed starter or have a clearly grown role, and his game must start within 60 hours. A college
   pick can be the Best bet. Write `research/lead.json`:
   `{"summary": "<1-2 sentences: the biggest news across the slate>", "best": {"key", "side", "why": "<2-3 sentences>", "sources": [urls]}}`
8. **Merge and publish.** `python merge_notes.py` (validates everything into `notes.json`), then
   `python picks.py picks.json`. Commit `notes.json picks.json slate.json` with the message
   `Research check <date> <AM|PM>` ending with the line
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, and push to main. If the push is
   rejected: `git pull --rebase origin main`, rerun `python picks.py picks.json`, commit, push.
   Don't commit the `research/` folder. **Always publish what you have**, even if some researchers failed.
   **Quality gate before you push:** run `python audit_top.py`. It rebuilds the Top 10s exactly as the
   app shows them and flags each pick. Any `NOT RESEARCHED` pick (the ranking shifts after research)
   gets a quick check now: 1-2 searches on availability, role and the line, then a note in
   `research/out/fix.json` (same format as a game file); any `RESEARCH SAYS` conflict means the note's
   side must be re-confirmed. Then rerun `python merge_notes.py`, `python picks.py picks.json` and the
   audit, at most twice, and push. Mention any remaining flags in your summary.
9. **Finish** with a short summary: games and props researched, notes (overs/unders), college picks,
   where the research or Kalshi disagreed with the app, the Best bet and why, and the top storyline.

## Light mode (quick news checks: every evening, Sunday inactives)

Used by the 4:34 PM daily check and the Sunday 11:34 AM inactives check, so the deep morning research
stays fresh without another full run. No subagents, a handful of searches in total.

1. Build the packets (`python research_packets.py`).
2. The prompt gives a window (for example "next 24 hours" or "next 3 hours"). For the games starting in
   that window, check the latest injury, practice, inactive and lineup news for the player behind every
   `target` and every anytime-TD note in `notes.json` (official team sites and beat writers first;
   search a team's news once and use it for all its players).
3. Edit `notes.json` directly; don't re-research or rewrite notes that haven't changed:
   - ruled out, inactive or suspended → `flag` "out";
   - a real late concern (downgraded to questionable/doubtful, limited snaps or minutes expected,
     a backup now starting ahead of him) → `flag` "caution", `adj` lowered by 1, and add the news to
     the note in one sentence;
   - news that clearly helps (a teammate ruled out, a starter role confirmed) → raise `adj` by 1
     (max +2) and add one sentence.
   Update `"updated"` to the current UTC time.
4. `python picks.py picks.json`, then `python audit_top.py`: for any `NOT RESEARCHED` pick whose game
   is in the window, do a quick availability, role and line check (1-2 searches) and add a short note
   to `notes.json` (side, flag, adj, conf, note, sources), then rerun picks.py.
5. Commit `notes.json picks.json slate.json` as `News check <date>`
   (or `Inactives check <date>`) ending with the Co-Authored-By line, push (if rejected:
   `git pull --rebase origin main`, rerun picks.py, commit, push).
6. Finish with one or two lines: who was ruled out, flagged or upgraded.

## Game researcher brief

> You research a batch of games for a player-prop app. Your batch is `research/batches/batch-<n>.json`
> (a list of packet ids); each packet is `research/packets/<id>.json`. The numbers in the packet are
> already in the app; find what they can't show. Use WebSearch and WebFetch and open the actual articles
> (team sites, beat writers, injury and practice reports, expert previews), not just snippets.
> Budget: about 4 searches per game plus 1-2 per target. Do the `full` games first.
>
> **Per game:** practice and injury reports for both sides (including the opposing defense), starters
> and depth-chart or rotation changes, coach/coordinator comments on usage or game plan, the expected
> script, weather for outdoor football, line moves, and what credible previews say about these props.
>
> **Per target prop**, write one specific sentence for each angle where you found something real (skip
> angles with nothing new; never restate the packet's numbers as a finding):
> - **availability**: status and the practice trend through the week (DNP → limited → full is a good
>   sign; limited all week or a Friday downgrade is a warning), limitations, minutes restrictions.
> - **role**: snaps, routes, targets/touches or minutes in the last 2-3 games; who absorbs injured
>   teammates' work; is he actually starting.
> - **matchup**: how this defense defends the stat this season, scheme/coverage, missing defenders.
> - **script**: how spread, total, pace and game plan shape his volume.
> - **conditions**: weather, wind, rest, travel.
> - **market**: Kalshi vs the 52.4% break-even of a -110 bet, line moves, consensus. If Kalshi is under
>   45% for the side you like, find out why. If the line quoted in current previews differs from the packet's
>   `line` (ESPN's DraftKings feed can lag a day or more), say so and give the current number.
> - **experts**: what credible previews say and why, in your own words.
> **Team news flows to every prop it touches.** When a game-level finding changes a team's outlook (a
> QB change or limited QB, a top receiver or back out or questionable, offensive-line injuries, a new
> play-caller), revisit every target AND `other_prop` on that team and the opponent, and write a note for
> each one the news moves (a backup QB starting usually means caution on his receivers' overs and on
> the QB-dependent props; a WR1 out usually supports the WR2/TE's volume).
>
> Then the verdict: `side`, `adj` (+2 strong, +1 mild, 0 nothing, -1 mild concern, -2 strong concern,
> for that side), `flag` (`out` / `caution` / `support` / `neutral`), `conf` (`high` = confirmed by an
> official report or team source plus at least one more independent source; `medium` = one solid
> source or clear usage data; `low` = inference or thin sourcing) and a one-sentence `note` (max 35 words) with the main non-stat reason.
> **Scan the whole board.** `other_props` lists every other prop in the game. After the targets, run
> down that list with what you've learned about the game (injuries, roles, script) and add a note for
> any prop the news clearly moves, or where you find a real edge (at most 3 per game).
>
> **Anytime TDs.** Each `full` game has `td_candidates`: the likeliest scorers with Kalshi's "1+ TD"
> price (`kalshi_1plus`) and their TD history. TDs come from red-zone and goal-line roles the numbers
> barely show, so check: who gets carries and targets inside the 10 and 5, goal-line packages, the
> opponent's red-zone defense, the team's implied points, and injuries that shift those roles. Pick at
> most 2 per game, only where your estimate of his chance to score is clearly above Kalshi's price, and
> write a note with `side` "over" (= scores), `adj` +1 or +2 and the red-zone reason. Use the key exactly
> as given (it ends in `|td`).
> Facts only, your own words: no quotes, usernames, copied picks, hype or guarantees.
>
> Write one file per game, `research/out/<packet id>.json`:
> ```
> {"game": "<id>", "summary": "<2-3 sentences: the storyline that matters for props>",
>  "sources": ["<urls>"],
>  "notes": {"<key copied exactly>": {"side": "over", "flag": "support", "adj": 1, "conf": "medium",
>     "note": "...", "detail": {"availability": "...", "role": "...", "matchup": "...", "script": "...",
>     "conditions": "...", "market": "...", "experts": "..."}, "sources": ["<urls you read>"]}},
>  "best_candidate": {"key": "...", "side": "over", "why": "<2-3 sentences>", "sources": ["..."]} or null}
> ```
> Every note needs at least one source you actually read. Reply with one line: games done, notes
> (overs/unders), and your best candidate.

## College researcher brief

> You find the best college football player props of the week for a prop app that has every FBS
> player's game logs but no sportsbook lines in its feed. Read `research/packets/CFB-week.json`: the games
> in the next 60 hours with spread/total and each team's main players (`key_prefix`, position, this
> season's averages and last 3 games). Work in three passes. Budget: about 25 searches in total.
>
> **Pass 1: collect ALL the player props for the big games.** Pick the 8 biggest games (ranked teams,
> national TV, high totals). For each, find the full list of posted player props (every QB, RB and WR
> line: passing yards, completions, attempts, passing TDs, rushing yards, carries, receptions, receiving
> yards, rush+rec yards) from reputable odds pages: BettingPros prop pages, Covers, Action Network,
> VSiN, OddsShark, FanDuel/DraftKings research pages, ESPN. Skip anonymous picks sites and lines given as
> whole numbers unless a named book posts them. Record each line exactly as posted (it usually ends in
> .5) and the book it's quoted for ("consensus" if the page averages books). Aim for 40-80 lines. Write
> them to `research/out/CFB-week.json` as `{"game": "CFB-week", "lines": [{"key": "<key_prefix>|<market>",
> "line": 245.5, "book": "FanDuel", "source": "<url>"}, ...]}`. Players not in the packet: look them up
> in `cfb_data.json` (`players`: `id`, `n` name, `t` team) to get the id.
>
> **Pass 2: screen them all.** Run `python cfb_screen.py`. It scores every line with the app's numbers:
> season and last-5 hit rate at the line, average, last 3 games, and how the opponent has defended that
> stat (rank, 1 = allows the most). Take the best 12 edges, at least two-thirds overs.
>
> **Pass 3: research those 12** beyond the numbers: availability and practice news, depth chart and
> snaps, the opponent's defense and missing defenders, game script from the spread/total, weather,
> line movement, and what credible previews say. Keep the 8-10 that hold up (an under only when the case
> is clearly stronger than any over) and add them to the same file:
> ```
> {"game": "CFB-week", "summary": "<2-3 sentences on the week's college storylines>", "sources": [...],
>  "lines": [ ...every line from pass 1... ],
>  "notes": {"<key>": {"side", "flag", "adj", "conf", "note", "detail": {...}, "sources": [...]}},
>  "best_candidate": {...} or null}
> ```
> Markets: `pyd` passing yards, `cmp` completions, `att` attempts, `ptd` passing TDs, `ryd` rushing
> yards, `car` carries, `rec` receptions, `recyd` receiving yards, `rry` rush+rec yards. Every note needs
> a source you read. Facts only, your own words. Reply with one line: games covered, lines collected,
> picks (overs/unders), best candidate.
