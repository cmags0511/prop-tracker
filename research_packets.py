"""Build one research packet per upcoming game for the twice-daily research check (see RESEARCH.md).

Each packet (research/packets/<id>.json) holds everything the app already knows about a game, so the
researcher can spend its searches on what the app CAN'T see: the spread/total and kickoff weather,
both injury reports, the starting lineups from the depth charts, and every prop with a DraftKings line,
with its recent form, matchup rank, Kalshi market probability and whether it's in the app's Top lists.

Usage: python research_packets.py [--hours 60] [--quick-hours 96]
Prints a one-line index of the packets: id, tier (full / quick), kickoff, props and Top-list picks.
"""
import json, os, sys, shutil, datetime as dt

ARGS = dict(zip(sys.argv[1::2], sys.argv[2::2]))
FULL_H = float(ARGS.get("--hours", 60))
QUICK_H = float(ARGS.get("--quick-hours", 96))
OUTDIR = "research/packets"
OUT_ST = {"Out", "Doubtful", "Injured Reserve", "Suspension"}


def load(f, d=None):
    try:
        return json.load(open(f))
    except Exception:
        return d if d is not None else {}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    slate = load("slate.json", {"props": []})["props"]
    picks = load("picks.json")
    ctx = load("context.json")
    data = load("props_data.json")
    cfb = load("cfb_data.json")
    if cfb:
        data["CFB"] = cfb
    top = {}
    for lk in ("picksOver", "picks"):
        for i, c in enumerate(picks.get(lk, [])):
            top.setdefault(c["key"], f"{'overs' if lk == 'picksOver' else 'all'} #{i + 1}")
    for lk in ("byMarketOver", "byMarket"):
        for v in picks.get(lk, {}).values():
            for i, c in enumerate(v):
                top.setdefault(c["key"], f"{c['label']} #{i + 1}")
    # games
    games = {}
    for p in slate:
        t = dt.datetime.fromisoformat(p["t"])
        h = (t - now).total_seconds() / 3600
        if h <= 0 or h > QUICK_H:
            continue
        meta = data.get(p["lg"], {})
        up = next((u for u in meta.get("upcoming", []) if dt.datetime.fromisoformat(u[0]) == t and p["team"] in (u[1], u[2])), None)
        away, home = (up[1], up[2]) if up else ((p["opp"], p["team"]) if p.get("home") else (p["team"], p["opp"]))
        gid = f"{p['lg']}-{away}-at-{home}-{t.astimezone(dt.timezone.utc):%m%d}"
        g = games.setdefault(gid, {"id": gid, "lg": p["lg"], "away": away, "home": home, "kickoff": p["t"],
                                   "tier": "full" if h <= FULL_H else "quick", "hours_to_kickoff": round(h, 1),
                                   "spread_home": up[3] if up else None, "total": up[4] if up else None, "props": []})
        g["props"].append({k: p.get(k) for k in ("key", "name", "team", "pos", "depth", "label", "line", "avg10", "l10_over", "n10",
                                                  "matchup", "gap", "lean", "score", "market_over", "status", "teammates_out",
                                                  "missed_last")} | {"in_top": top.get(p["key"])})
    # injuries, depth and weather per game
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
        g["props"].sort(key=lambda x: (x["in_top"] is None, -(x["score"] or 0)))
    if os.path.isdir(OUTDIR):
        shutil.rmtree(OUTDIR)
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs("research/out", exist_ok=True)
    for g in sorted(games.values(), key=lambda g: g["kickoff"]):
        json.dump(g, open(f"{OUTDIR}/{g['id']}.json", "w"), indent=1)
        n_top = sum(1 for x in g["props"] if x["in_top"])
        print(f"{g['id']:28} {g['tier']:5} {g['kickoff'][:16]}  {len(g['props']):3} props  {n_top:2} in Top lists")
    if not games:
        print("no games with DraftKings lines in the window")


if __name__ == "__main__":
    main()
