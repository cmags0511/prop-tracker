"""Build the research packets for the research check (see RESEARCH.md).

Research is the expensive part of the app, so it goes where people look: the props the app actually
shows (the Top 10s, each game's Top 5, Kalshi gaps for the Best bet). For each upcoming game a packet
(research/packets/<id>.json) holds the game context (spread/total, weather, both injury reports with
practice notes, starters), its TARGET props with everything the app knows about them, and every other
prop in the game in compact form so the researcher can scan the whole board. Games are then grouped into at most 4 batches
(research/batches/batch-<n>.json), one researcher per batch.

College football has no DraftKings prop lines in the app's feed, so it gets one extra packet
(research/packets/CFB-week.json): the week's games and each team's main players with their numbers,
for a researcher who finds published prop lines and picks the best college props.

Usage: python research_packets.py [--hours 60] [--quick-hours 96] [--batches 4]
"""
import json, os, sys, shutil, datetime as dt

ARGS = dict(zip(sys.argv[1::2], sys.argv[2::2]))
FULL_H = float(ARGS.get("--hours", 60))
QUICK_H = float(ARGS.get("--quick-hours", 96))
N_BATCH = int(ARGS.get("--batches", 4))
MAX_TARGETS = {"NFL": 36, "NBA": 24}
OUT_ST = {"Out", "Doubtful", "Injured Reserve", "Suspension"}
FIELDS = ("key", "name", "team", "pos", "depth", "label", "line", "avg10", "l10_over", "n10", "matchup", "gap", "lean",
          "score", "market_over", "status", "teammates_out", "missed_last")


def load(f, d=None):
    try:
        return json.load(open(f))
    except Exception:
        return d if d is not None else {}


def targets(slate, picks, now):
    """{key: why it's a target} for the props people will see, capped per league"""
    why = {}
    add = lambda k, r: why.setdefault(k, r)
    for i, c in enumerate(picks.get("picksOver", [])[:12]):
        add(c["key"], f"overs Top 10 #{i + 1}")
    for i, c in enumerate(picks.get("picks", [])[:8]):
        add(c["key"], f"Top 10 #{i + 1}")
    seen = {}
    for c in picks.get("gamesOver", []):  # each game's Top 5 (overs), first 3
        g = (c["lg"], c["t"], *sorted((c["team"], c["opp"])))
        if seen.get(g, 0) < 3:
            seen[g] = seen.get(g, 0) + 1
            add(c["key"], "game Top 5")
    # scouting for the Best bet: overs Kalshi likes at DraftKings' line, and role bumps from injuries
    live = [p for p in slate if dt.datetime.fromisoformat(p["t"]) > now]
    for p in sorted([p for p in live if (p.get("market_over") or 0) >= .56], key=lambda p: -p["market_over"])[:6]:
        add(p["key"], f"Kalshi {round(p['market_over'] * 100)}% over")
    for p in sorted([p for p in live if p.get("teammates_out") and p.get("lean") == "over"], key=lambda p: -p["score"])[:4]:
        add(p["key"], "teammate out")
    out, n = {}, {}
    order = {k: i for i, k in enumerate(why)}
    for k in sorted(why, key=order.get):
        lg = k.split("|")[0]
        if n.get(lg, 0) < MAX_TARGETS.get(lg, 20):
            out[k] = why[k]
            n[lg] = n.get(lg, 0) + 1
    return out


def td_candidates(lg, teams, kickoff, data, mkts):
    """the likeliest anytime-TD scorers in a game: Kalshi's "1+ TD" price plus each player's TD history"""
    if lg != "NFL":
        return []
    meta = data.get(lg, {})
    cols = meta.get("cols", [])
    day = dt.datetime.fromisoformat(kickoff).astimezone(dt.timezone(dt.timedelta(hours=-4)))
    code = f"{day:%y}{day.strftime('%b').upper()}{day:%d}"
    out = []
    for pl in meta.get("players", []):
        if pl["t"] not in teams or pl.get("p") not in ("RB", "WR", "TE", "QB"):
            continue
        lad = ((mkts.get(lg) or {}).get(pl["id"]) or {}).get("td")
        k = None
        if lad and code in lad.get("g", ""):
            k = next((pr for s, pr, _ in lad["k"] if s == .5), None)
        gs = [dict(zip(cols, r)) for r in pl["g"]]
        cur = [g for g in gs if g["date"] >= meta.get("curStart", "")]
        l10 = gs[-10:]
        if not cur:
            continue
        rate = lambda a: round(sum(1 for g in a if g["td"] > 0) / len(a), 2) if a else None
        if k is None and (rate(l10) or 0) < .3:
            continue
        out.append({"key": f"{lg}|{pl['id']}|td", "name": pl["n"], "team": pl["t"], "pos": pl.get("p"),
                    "kalshi_1plus": k, "td_games_l10": rate(l10), "td_games_season": rate(cur),
                    "season_tds": sum(g["td"] for g in cur), "season_games": len(cur)})
    return sorted(out, key=lambda x: -(x["kalshi_1plus"] if x["kalshi_1plus"] is not None else x["td_games_l10"] * .8))[:6]


def cfb_packet(cfb, now):
    """this week's college games and each team's main players (by this season's volume)"""
    cols = cfb.get("cols", [])
    ups = [u for u in cfb.get("upcoming", []) if 0 < (dt.datetime.fromisoformat(u[0]) - now).total_seconds() / 3600 <= FULL_H]
    if not ups or not cols:
        return None
    teams = {t for u in ups for t in (u[1], u[2])}
    by_team = {}
    for p in cfb.get("players", []):
        if p["t"] not in teams:
            continue
        cur = [dict(zip(cols, r)) for r in p["g"] if dict(zip(cols, r))["date"] >= cfb["curStart"]]
        if len(cur) < 2:
            continue
        avg = lambda k: round(sum(g[k] for g in cur) / len(cur), 1)
        rec = {"key_prefix": f"CFB|{p['id']}", "name": p["n"], "pos": p["p"], "games": len(cur),
               "avg": {k: avg(k) for k in ("cmp", "att", "pyd", "ptd", "car", "ryd", "rec", "recyd")},
               "last3": {k: [g[k] for g in cur[-3:]] for k in ("pyd", "ryd", "recyd", "rec")}}
        by_team.setdefault(p["t"], []).append(rec)
    keep = {}
    for tm, ps in by_team.items():
        pick = sorted([p for p in ps if p["pos"] == "QB"], key=lambda p: -p["avg"]["att"])[:1]
        pick += sorted([p for p in ps if p["pos"] == "RB"], key=lambda p: -p["avg"]["car"])[:2]
        pick += sorted([p for p in ps if p["pos"] == "WR"], key=lambda p: -p["avg"]["recyd"])[:3]
        keep[tm] = pick
    games = [{"away": u[1], "home": u[2], "kickoff": u[0], "spread_home": u[3], "total": u[4],
              "players": {u[1]: keep.get(u[1], []), u[2]: keep.get(u[2], [])}} for u in sorted(ups, key=lambda u: u[0])]
    return {"id": "CFB-week", "lg": "CFB", "markets": ["pyd", "cmp", "att", "ptd", "ryd", "car", "rec", "recyd", "rry"],
            "note": "Keys are key_prefix + '|' + market, e.g. CFB|4432577|pyd. Team codes are ESPN's.", "games": games}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    slate = load("slate.json", {"props": []})["props"]
    picks = load("picks.json")
    ctx = load("context.json")
    mkts = load("markets.json")
    data = load("props_data.json")
    cfb = load("cfb_data.json")
    if cfb:
        data["CFB"] = cfb
    for lg in ("NFL", "NBA"):  # current team from ESPN's depth charts (trades/signings since his last game)
        for pl in (data.get(lg) or {}).get("players", []):
            d = ((ctx.get("depth") or {}).get(lg) or {}).get(str(pl.get("e") or pl["id"]))
            if d and d.get("t"):
                pl["t"] = d["t"]
    tg = targets(slate, picks, now)
    games = {}
    for p in slate:
        t = dt.datetime.fromisoformat(p["t"])
        h = (t - now).total_seconds() / 3600
        if h <= 0 or h > QUICK_H or p["lg"] == "CFB":  # college has its own researcher (CFB-week)
            continue
        meta = data.get(p["lg"], {})
        up = next((u for u in meta.get("upcoming", []) if dt.datetime.fromisoformat(u[0]) == t and p["team"] in (u[1], u[2])), None)
        away, home = (up[1], up[2]) if up else (p["team"], p["opp"])
        gid = f"{p['lg']}-{away}-at-{home}-{t.astimezone(dt.timezone.utc):%m%d}"
        g = games.setdefault(gid, {"id": gid, "lg": p["lg"], "away": away, "home": home, "kickoff": p["t"],
                                   "tier": "full" if h <= FULL_H else "quick", "hours_to_kickoff": round(h, 1),
                                   "spread_home": up[3] if up else None, "total": up[4] if up else None,
                                   "targets": [], "other_props": []})
        row = {k: p.get(k) for k in FIELDS}
        if p["key"] in tg:
            g["targets"].append(row | {"why_target": tg[p["key"]]})
        else:
            g["other_props"].append({k: p.get(k) for k in ("key", "name", "label", "line", "avg10", "lean", "score", "market_over", "depth")})
    games = {k: g for k, g in games.items() if g["targets"]}  # only games with something people will see
    inj, dep, wx = ctx.get("injuries", {}), ctx.get("depth", {}), ctx.get("weather", {})
    for g in games.values():
        lg, teams = g["lg"], (g["away"], g["home"])
        g["injuries"] = {tm: sorted([{"name": i["n"], "pos": i["pos"], "status": i["s"], "injury": i.get("inj"), "note": i.get("c")}
                                     for i in inj.get(lg, {}).values() if i.get("t") == tm and i["s"] != "Injured Reserve"],
                                    key=lambda x: (x["status"] not in OUT_ST, x["pos"])) for tm in teams}
        names = {}
        for pl in data.get(lg, {}).get("players", []):
            d = dep.get(lg, {}).get(str(pl.get("e") or pl["id"]))
            if pl["t"] in teams and d and d["role"] == "starter" and d["slot"] != "DEF":
                names.setdefault(pl["t"], []).append(f"{d['slot']} {pl['n']}" + (" (moved up)" if d.get("moved_up") else ""))
        g["starters"] = {tm: sorted(names.get(tm, [])) for tm in teams}
        t = dt.datetime.fromisoformat(g["kickoff"]).astimezone(dt.timezone.utc)
        w = wx.get(f"{lg}|{g['away']}@{g['home']}|{t:%Y-%m-%d}")
        g["weather"] = None if not w else ("indoor" if w.get("indoor") else {k: w.get(k) for k in ("wind", "gust", "rain", "temp")} | {"venue": w.get("venue")})
        # every other prop in the game, compact, so the researcher can scan the whole board for edges
        g["other_props"] = sorted(g["other_props"], key=lambda x: -(x["score"] or 0))
        g["td_candidates"] = td_candidates(lg, teams, g["kickoff"], data, mkts) if g["tier"] == "full" else []
    for d in ("research/packets", "research/batches"):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
    os.makedirs("research/out", exist_ok=True)
    order = sorted(games.values(), key=lambda g: (g["tier"] != "full", g["kickoff"]))
    for g in order:
        json.dump(g, open(f"research/packets/{g['id']}.json", "w"), indent=1)
    # batches: balance the number of target props, keeping kickoff order
    nb = max(1, min(N_BATCH, len(order)))
    batches = [[] for _ in range(nb)]
    load_ = [0] * nb
    for g in order:
        i = load_.index(min(load_))
        batches[i].append(g["id"])
        load_[i] += len(g["targets"]) + 3  # +3: the game-level research
    for i, b in enumerate(batches):
        if b:
            json.dump(b, open(f"research/batches/batch-{i + 1}.json", "w"))
            print(f"batch-{i + 1}: {len(b)} games, {sum(len(games[x]['targets']) for x in b)} target props: {', '.join(b)}")
    cp = cfb_packet(cfb, now) if cfb else None
    if cp:
        json.dump(cp, open("research/packets/CFB-week.json", "w"), indent=1)
        print(f"CFB-week: {len(cp['games'])} college games in the next {FULL_H:.0f} hours")
    if not games and not cp:
        print("nothing to research in the window")


if __name__ == "__main__":
    main()
