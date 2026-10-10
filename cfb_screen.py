"""Screen every college prop line the research collected against the app's numbers (see RESEARCH.md).

The college researcher first gathers ALL published player props for the week's biggest games into
research/out/CFB-week.json ("lines"). This script scores each one with the app's game logs, so the
researcher can spend its searches on the best few:
  season and last-5 hit rate at the line, average, last 3 games, and how the opponent has defended that
  stat this season (rank among FBS teams, 1 = allows the most).

Usage: python cfb_screen.py            prints the screen, best edges first (overs and unders)
       python cfb_screen.py --json     also writes research/cfb_screen.json
"""
import json, sys, datetime as dt

STAT = {"pyd": "pyd", "cmp": "cmp", "att": "att", "ptd": "ptd", "ryd": "ryd", "car": "car", "rec": "rec", "recyd": "recyd"}
POS = {"pyd": "QB", "cmp": "QB", "att": "QB", "ptd": "QB", "ryd": None, "car": None, "rec": None, "recyd": None, "rry": None}


def val(g, m):
    return g["ryd"] + g["recyd"] if m == "rry" else g[STAT[m]]


def main():
    cfb = json.load(open("cfb_data.json"))
    cols = cfb["cols"]
    try:
        lines = json.load(open("research/out/CFB-week.json")).get("lines", [])
    except Exception as e:
        sys.exit(f"no research/out/CFB-week.json lines yet ({e})")
    players = {p["id"]: p for p in cfb["players"]}
    cur = cfb["curStart"]
    games = {p["id"]: [dict(zip(cols, r)) for r in p["g"] if r[0] >= cur] for p in cfb["players"]}
    # what each defense allowed per game this season, per stat, from every player's logs
    allowed = {}
    for pid, gs in games.items():
        for g in gs:
            for m in list(STAT) + ["rry"]:
                allowed.setdefault(m, {}).setdefault(g["opp"], {}).setdefault(g["date"], 0)
                allowed[m][g["opp"]][g["date"]] += val(g, m)
    rank = {}
    for m, by in allowed.items():
        avg = {t: sum(d.values()) / len(d) for t, d in by.items() if len(d) >= 3}
        order = sorted(avg, key=lambda t: -avg[t])
        rank[m] = {t: (i + 1, len(order), round(avg[t], 1)) for i, t in enumerate(order)}
    nxt = {}
    now = dt.datetime.now(dt.timezone.utc)
    for u in cfb.get("upcoming", []):
        if dt.datetime.fromisoformat(u[0]) > now:
            for tm, opp in ((u[1], u[2]), (u[2], u[1])):
                nxt.setdefault(tm, opp)
    rows = []
    for ln in lines:
        try:
            _, pid, m = ln["key"].split("|")
            line = float(ln["line"])
        except Exception:
            continue
        p, gs = players.get(pid), games.get(pid) or []
        if not p or m not in POS or not gs:
            rows.append({"key": ln.get("key"), "error": "unknown player or market"})
            continue
        v = [val(g, m) for g in gs]
        over = lambda a: sum(x > line for x in a)
        opp = nxt.get(p["t"])
        rk = rank.get(m, {}).get(opp)
        s_hit = over(v) / len(v)
        l5 = v[-5:]
        edge = (s_hit - .5) * .6 + (over(l5) / len(l5) - .5) * .4 + ((sum(v) / len(v)) - line) / max(line, 1) * .5
        rows.append({"key": ln["key"], "name": p["n"], "team": p["t"], "opp": opp, "market": m, "line": line, "book": ln.get("book"),
                     "season_over": f"{over(v)}/{len(v)}", "last5_over": f"{over(l5)}/{len(l5)}", "avg": round(sum(v) / len(v), 1),
                     "last3": v[-3:], "opp_allows_rank": f"{rk[0]}/{rk[1]} ({rk[2]}/g)" if rk else None,
                     "lean": "over" if edge >= 0 else "under", "edge": round(abs(edge), 3)})
    rows.sort(key=lambda r: -r.get("edge", -1))
    for r in rows:
        if "error" in r:
            print(f"!! {r['key']}: {r['error']}")
        else:
            print(f"{r['edge']:.3f} {r['lean']:5} {r['name'][:22]:22} {r['team']:5} vs {str(r['opp']):5} {r['market']:5} {r['line']:6} "
                  f"season {r['season_over']:5} last5 {r['last5_over']:4} avg {r['avg']:6} last3 {r['last3']} opp {r['opp_allows_rank']}  [{r['book']}]")
    if "--json" in sys.argv:
        json.dump(rows, open("research/cfb_screen.json", "w"), indent=1)
    print(f"{len(rows)} lines screened")


if __name__ == "__main__":
    main()
