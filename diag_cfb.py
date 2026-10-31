"""One-off: for one college game, what player props do the books actually post, and do the unpriced players appear?"""
import json, os, sys, datetime as dt
os.environ.setdefault("ODDSPAPI_KEY", "")
import fetch_oddspapi as f
from fetch_odds import norm
from fetch_sgo import same_player
S = json.load(open("slate.json"))["props"]
tbl = json.load(open("oddspapi_markets.json"))["markets"]
now = dt.datetime.now(dt.timezone.utc)
for teams in (("NU", "ORE"), ("OU", "SC")):
    cs = [p for p in S if p["lg"] == "CFB" and tuple(sorted((p["team"], p["opp"]))) == tuple(sorted(teams))]
    un = [p for p in cs if p.get("po") is None or p.get("pu") is None]
    print(f"\n=== {teams}: {len(cs)} props, {len(un)} unpriced")
    t = dt.datetime.fromisoformat(cs[0]["t"])
    d = f.get("/fixtures", sportId=14, **{"from": str(now.date()), "to": str((now + dt.timedelta(days=2)).date())})
    hit = [x for x in d if x.get("tournamentId") == 27653 and abs(dt.datetime.fromisoformat(x["startTime"].replace("Z", "+00:00")) - t) < dt.timedelta(minutes=20)
           and all(any(f.team_fits("CFB", a, x, s) for s in (1, 2)) for a in teams)]
    print("fixtures matched:", [(x["participant1Name"], x["participant2Name"], x["fixtureId"]) for x in hit])
    if len(hit) != 1:
        continue
    o = f.get("/odds", fixtureId=hit[0]["fixtureId"], bookmaker="draftkings,fanduel,betmgm,pinnacle")
    allp = {}  # (type, player) -> {book: [lines]}
    for b, bv in (o.get("bookmakerOdds") or {}).items():
        for mid, m in (bv.get("markets") or {}).items():
            info = tbl.get(mid)
            for oid, oc in (m.get("outcomes") or {}).items():
                for pid, pl in (oc.get("players") or {}).items():
                    if pid != "0" and pl.get("playerName"):
                        allp.setdefault((info[0] if info else "other:" + mid, f.flip(pl["playerName"])), {}).setdefault(b, set()).add(info[1] if info else None)
    byt = {}
    for (ty, pn), bk in allp.items():
        byt.setdefault(ty, set()).add(pn)
    print("books:", list(o.get("bookmakerOdds") or {}))
    print("players per mapped type:", {k: len(v) for k, v in byt.items() if not k.startswith("other:")}, "| unmapped markets:", len({k for k in byt if k.startswith('other:')}))
    for p in un:
        nm = norm(p["name"])
        anyp = sorted({ty for (ty, pn) in allp if same_player(nm, pn)})
        print(f"  unpriced {p['market']:6} {p['name']:24} line {p['line']}: in feed as {anyp[:6]}")
    print("  priced sample names in feed:", sorted({pn for (ty, pn) in allp if ty == 'rec'})[:8])
