# Research playbook (the research check)

The app's numbers already cover recent form, the opponent's defense against his position, the game's
spread and total, minutes trends, the ESPN injury report and depth chart, kickoff wind and the Kalshi
market price. **Your job is what the numbers can't see**, for the props people actually look at.

The owner prefers **overs**; the app shows overs by default. Spend most of the effort on overs, but be
honest: if the research says under, say under.

**Budget.** Research runs on the owner's Claude usage, and an earlier version that researched every
prop in every game used it all up. Stay inside these limits: at most 4 NFL/NBA researchers plus 1
college researcher, about 4 searches per game for the game-level picture plus 1-2 per target prop,
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
6. **Choose the Best bet** from the researchers' `best_candidate`s: the single OVER where stats, matchup,
   role, conditions, market and news line up best (an under only if no over is sound). He must be a
   confirmed starter or have a clearly grown role, and his game must start within 60 hours. A college
   pick can be the Best bet. Write `research/lead.json`:
   `{"summary": "<1-2 sentences: the biggest news across the slate>", "best": {"key", "side", "why": "<2-3 sentences>", "sources": [urls]}}`
7. **Merge and publish.** `python merge_notes.py` (validates everything into `notes.json`), then
   `python picks.py picks.json`. Commit `notes.json picks.json slate.json` with the message
   `Research check <date> <AM|PM>` ending with the line
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, and push to main. If the push is
   rejected: `git pull --rebase origin main`, rerun `python picks.py picks.json`, commit, push.
   Don't commit the `research/` folder. **Always publish what you have**, even if some researchers failed.
8. **Finish** with a short summary: games and props researched, notes (overs/unders), college picks,
   where the research or Kalshi disagreed with the app, the Best bet and why, and the top storyline.

## Light mode (Sunday late-morning inactives check)

When the prompt says light mode: skip the researchers. Build the packets, then for the games starting
in the next 3 hours check the official inactives and late injury news (team sites, beat writers) for
every target. Update `notes.json` directly: set `flag` to `out` for anyone inactive, `caution` for a
real late concern, and leave everything else as it is. Then `python picks.py picks.json`, commit
(`Inactives check <date>`), push.

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
> - **availability**: status, practice reps, limitations, minutes restrictions.
> - **role**: snaps, routes, targets/touches or minutes in the last 2-3 games; who absorbs injured
>   teammates' work; is he actually starting.
> - **matchup**: how this defense defends the stat this season, scheme/coverage, missing defenders.
> - **script**: how spread, total, pace and game plan shape his volume.
> - **conditions**: weather, wind, rest, travel.
> - **market**: Kalshi vs the 52.4% break-even of a -110 bet, line moves, consensus. If Kalshi is under
>   45% for the side you like, find out why.
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
> If you find a strong edge in `other_props`, add a note for it too (at most 2 per batch).
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

> You pick the best college football player props of the week for a prop app that has every FBS
> player's game logs but no sportsbook lines. Read `research/packets/CFB-week.json`: the games in the
> next 60 hours with spread/total and each team's main players (`key_prefix`, position, this season's
> averages and last 3 games). Budget: about 15 searches in total.
>
> 1. Pick the 6 biggest games (ranked teams, national TV, high totals) and find their published
>    player prop lines in prop previews and odds articles from reputable outlets (Action Network,
>    Covers, VSiN, Pickswise, OddsShark, ESPN, The Athletic, team beat writers). Skip anonymous picks
>    sites. Record the line exactly as quoted (usually ending in .5) and the book it's quoted for; if an
>    article gives no book, use "consensus".
> 2. Choose the 8-10 best props, at least two-thirds overs (the owner prefers overs; include an under
>    only when the case is clearly stronger): compare each line with the player's averages and last 3
>    games in the packet, then check availability, role, the opponent's defense, script and weather.
> 3. Write `research/out/CFB-week.json`:
> ```
> {"game": "CFB-week", "summary": "<2-3 sentences on the week's college storylines>", "sources": [...],
>  "lines": [{"key": "<key_prefix>|<market>", "line": 245.5, "book": "FanDuel", "source": "<url>"}],
>  "notes": {"<same key>": {"side", "flag", "adj", "conf", "note", "detail": {...}, "sources": [...]}},
>  "best_candidate": {...} or null}
> ```
> Markets: `pyd` passing yards, `cmp` completions, `att` attempts, `ptd` passing TDs, `ryd` rushing
> yards, `car` carries, `rec` receptions, `recyd` receiving yards, `rry` rush+rec yards. Lines must end
> in .0 or .5. Every pick needs both a `lines` entry and a note with a source. Same rules: facts only,
> your own words. Reply with one line: games covered, picks (overs/unders), best candidate.
