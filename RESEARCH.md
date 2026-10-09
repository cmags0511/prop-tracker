# Research playbook (the twice-daily research check)

The app's numbers already cover recent form, the opponent's defense against his position, the game's
spread and total, minutes trends, the ESPN injury report and depth chart, kickoff wind and the Kalshi
market price. **Your job is everything the numbers can't see.** Research each prop like a beat writer
and a sharp bettor would, from several angles, and say what you found in your own words.

The owner prefers **overs**; the app shows overs by default. Spend most of the effort finding and
verifying strong overs, but be honest: if the research says under, say under.

## Steps

1. **Get the repo.** `add_repo` (owner `cmags0511`, repo `prop-tracker`, access `push`), then
   `git clone --depth 1 https://github.com/cmags0511/prop-tracker` and work inside it.
2. **Build the packets.** `python research_packets.py`. It prints one line per game with props:
   `full` games (kickoff within 60 hours) get the deep research below; `quick` games (later) get a
   shorter pass. Each packet in `research/packets/` has the game's spread/total and weather, both
   teams' injury reports with practice notes, the starters from the depth charts, and every prop with a
   DraftKings line: recent form (`l10_over`/`n10`, `avg10`), matchup rank (1 = that defense allows the
   most to his position), `gap` (line vs his average), `lean` (stats side), the app's `score`,
   `market_over` (Kalshi's probability of the over at DraftKings' line), `depth` and `in_top` (which
   app list it's on).
3. **Research every game in parallel: one researcher per game.** Use the Agent tool to start one
   subagent per game, all in one message so they run at the same time (if there are more than about 12
   games, run them in two waves; if the Agent tool isn't available, do the games yourself one by one).
   Give each subagent the "Game researcher brief" below with its packet path filled in. Each writes
   `research/out/<packet id>.json`.
4. **Check the write-ups.** Open each `research/out/*.json`. Send a researcher back if it skipped props
   that are in the Top lists, wrote notes that only restate the numbers, or gave no sources.
5. **Choose the Best bet** from the researchers' `best_candidate`s and the notes: the single OVER where
   stats, matchup, role, conditions, market and news line up best (an under only if no over is sound).
   He must be a confirmed starter or have a clearly grown role, his game must be a `full` game, and his
   note must have the same side, adj +2 and conf high. Write `research/lead.json`:
   `{"summary": "<1-2 sentences: the biggest news across the slate>", "best": {"key", "side", "why": "<2-3 sentences>", "sources": [urls]}}`
6. **Merge and publish.** `python merge_notes.py` (validates everything and writes `notes.json`), then
   `python picks.py picks.json`. Commit `notes.json picks.json slate.json` with the message
   `Research check <date> <AM|PM|midday>` ending with the line
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, and push to main. If the push is
   rejected: `git pull --rebase origin main`, rerun `python picks.py picks.json`, commit, push.
   Don't commit the `research/` folder.
7. **Finish** with a short summary: games and props researched, how many notes (overs/unders), where
   the research or Kalshi disagreed with the app's picks, the Best bet and why, and the top storyline.

## Game researcher brief

> You are researching one game for a player-prop app. Read the packet at `research/packets/<id>.json`.
> The app already knows the numbers in it; your job is what the numbers can't see. Use WebSearch and
> WebFetch, and open the actual articles (team sites, beat writers, injury and practice reports,
> expert previews), not just search snippets.
>
> **First, the game as a whole (5-8 searches):** official injury report and practice participation
> (or NBA shootaround/injury news); who's in, out or limited on both sides, including the opposing
> defense; starters and any depth-chart or rotation change; coach and coordinator comments about
> usage, scheme or game plan; the expected script from the spread and total; pace; rest and travel
> (short week, back-to-back, long trip); weather for outdoor football; the betting market (line moves,
> consensus) and expert previews of this game's props (Action Network, Covers, VSiN, ESPN, The Athletic,
> Rotowire, PFF, team beat writers; Reddit r/sportsbook and team subreddits for sentiment).
>
> **Then each prop.** Cover every prop with `in_top` set, every prop whose player is affected by news
> you found, and any other prop where you find a real edge. For quick-tier games, cover the `in_top`
> props with at least an availability and role check. For each, work through these angles and write
> one or two specific sentences for every angle where you found something (skip an angle only if
> there's genuinely nothing):
> - **availability**: his status, practice reps, any limitation or minutes restriction.
> - **role**: snap share, routes, targets/touches or minutes and usage over the last 2-3 games; depth
>   chart; who absorbs work from injured teammates. Confirm he's actually starting.
> - **matchup**: how the opponent defends this stat this season and how that's changed (scheme,
>   coverage, missing defenders, the specific defender he'll face); for defensive props, the offense.
> - **script**: how the spread, total, pace and game plan shape his volume (trailing teams throw more,
>   big favorites run late, etc.).
> - **conditions**: weather, wind, surface, rest, travel, altitude.
> - **market**: the Kalshi probability vs the 52.4% break-even of a -110 bet, line movement since open,
>   where sharp money or consensus sits. If Kalshi is under 45% for the side you like, find out why.
> - **experts**: what credible previews say about this prop and why, in your own words (never copy
>   picks, quotes or usernames).
>
> Then give a verdict: `side` (the side your research favors), `adj` (+2 strong, +1 mild, 0 nothing
> material, -1 mild concern, -2 strong concern, for that side), `flag` (`out` if he won't play or news
> breaks every bet on him; `caution` for real concerns; `support` when news backs your side; `neutral`
> otherwise), `conf` (`high`/`medium`/`low`: how solid the evidence is) and a one-sentence `note` (max
> 35 words) naming the main non-stat reason. Facts only, no hype, no guarantees.
>
> Write `research/out/<id>.json`:
> ```
> {"game": "<id>", "summary": "<2-3 sentences: the storyline that matters for props>",
>  "sources": ["<urls for the game-level findings>"],
>  "notes": {"<prop key from the packet>": {"side": "over", "flag": "support", "adj": 1, "conf": "medium",
>     "note": "...", "detail": {"availability": "...", "role": "...", "matchup": "...", "script": "...",
>     "conditions": "...", "market": "...", "experts": "..."}, "sources": ["<urls>"]}},
>  "best_candidate": {"key": "...", "side": "over", "why": "<2-3 sentences>", "sources": ["..."]} or null}
> ```
> Keys must be copied exactly from the packet. Every note needs at least one source URL you actually
> read. Reply with one line: props covered, overs/unders, and your best candidate.
