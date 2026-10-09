"""Keep an honest, graded record of the app's Top 10 picks in record.json.

Each run:
  1. Lock in picks. For each league, the app's "Best overall" Top 10 (same rules as the page:
     best play per player across every prop, players ruled out by the injury report or the daily
     news check removed) is saved for games that haven't started, both over every side ("all") and
     overs only ("over"); each entry lists the Top 10s it was in. Until kickoff a pick can still change or drop out
     as lines move; once its game starts it is frozen. So the record is the Top 10 as it stood
     just before each game.
  2. Grade frozen picks against the box score: win, loss, push, or void (player didn't play).

Usage: python record.py [record.json]
"""
import json, sys, datetime as dt
from zoneinfo import ZoneInfo
from picks import stat, OUT_STATUS

OUT = sys.argv[1] if len(sys.argv) > 1 else "record.json"
ET = ZoneInfo("America/New_York")
TOP = 10


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def main():
    now = dt.datetime.now(dt.timezone.utc)
    data = json.load(open("props_data.json"))
    try:
        data["CFB"] = json.load(open("cfb_data.json"))
    except Exception:
        pass
    picks = load("picks.json", {})
    notes = load("notes.json", {})
    rec = load(OUT, {"picks": []})

    # players the news check ruled out (only trust notes from the last 36 hours)
    out_players = set()
    try:
        if notes.get("updated") and now - dt.datetime.fromisoformat(notes["updated"].replace("Z", "+00:00")) < dt.timedelta(hours=36):
            out_players = {"|".join(k.split("|")[:2]) for k, v in notes.get("notes", {}).items() if v.get("flag") == "out"}
    except Exception:
        pass

    def start(p):
        return dt.datetime.fromisoformat(p["t"])

    entries = {(e["key"], e["t"]): e for e in rec["picks"]}

    # 1. current pre-game Top 10 per league ("Best overall": best play per player across all props),
    #    once over every side and once overs only (the app's default view); each entry notes which lists it was in
    out_ids = set()
    if True:
        try:
            ctx = json.load(open("context.json"))
            for lg, inj in (ctx.get("injuries") or {}).items():
                fetched = dt.datetime.fromisoformat((ctx.get("fetched") or {}).get(lg) or ctx["built"])
                if now - fetched > dt.timedelta(hours=30):
                    continue  # stale report: don't let it drop anyone
                for aid, i in inj.items():
                    if i["s"] in OUT_STATUS:
                        out_ids.add((lg, aid))
        except Exception:
            pass
    espn = {lg: {p["id"]: str(p.get("e") or p["id"]) for p in data[lg]["players"]} for lg in ("NFL", "NBA", "CFB") if lg in data}
    for lg in [l for l in ("NFL", "NBA", "CFB") if l in data]:
        tops = {}
        for setname, lk, bk in (("all", "picks", "byMarket"), ("over", "picksOver", "byMarketOver")):
            pool = {}
            for c in list(picks.get(lk, [])) + [c for k, v in picks.get(bk, {}).items() if k.startswith(lg + "|") for c in v]:
                if c["lg"] == lg and (setname == "all" or c["side"] == "over"):
                    pool[c["key"]] = c
            top, seen = [], set()
            for c in sorted(pool.values(), key=lambda c: -c["score"]):
                if start(c) <= now or f"{lg}|{c['id']}" in out_players or (lg, espn[lg].get(c["id"])) in out_ids or c["id"] in seen:
                    continue
                seen.add(c["id"])
                top.append(c)
                if len(top) == TOP:
                    break
            tops[setname] = top
        cur = {}
        for setname, top in tops.items():
            for c in top:
                cur.setdefault((c["key"], c["t"]), (c, []))[1].append(setname)
        # drop not-yet-started picks that fell out of both lists
        for k, e in list(entries.items()):
            if e["lg"] == lg and e["status"] == "pending" and start(e) > now and k not in cur:
                del entries[k]
        for k, (c, sets) in cur.items():
            entries[k] = {
                "key": c["key"], "lg": lg, "id": c["id"], "name": c["name"], "team": c["team"], "opp": c["opp"],
                "home": c["home"], "t": c["t"], "market": c["market"], "label": c["label"], "side": c["side"],
                "line": c["line"], "score": c["score"], "l10": c["l10"], "sets": sets, "status": "pending", "result": None,
            }

    # 1b. the research check's Best bet: keep the current one until its game starts, then it's locked
    best = {(e["key"], e["t"]): e for e in rec.get("best", [])}
    # a pending Best bet whose player was ruled out before kickoff is dropped, not graded as a void
    for k, e in list(best.items()):
        if e["status"] == "pending" and start(e) > now and (f"{e['lg']}|{e['id']}" in out_players or (e["lg"], espn.get(e["lg"], {}).get(e["id"])) in out_ids):
            del best[k]
    b = picks.get("best")
    if b and start(b) > now and f"{b['lg']}|{b['id']}" not in out_players:
        for k, e in list(best.items()):
            if e["status"] == "pending" and start(e) > now:
                del best[k]
        best[(b["key"], b["t"])] = {
            "key": b["key"], "lg": b["lg"], "id": b["id"], "name": b["name"], "team": b["team"], "opp": b["opp"],
            "home": b["home"], "t": b["t"], "market": b["market"], "label": b["label"], "side": b["side"],
            "line": b["line"], "score": b["score"], "why": b.get("why_research", ""), "status": "pending", "result": None,
        }

    # 2. grade picks whose games have started
    players = {lg: {p["id"]: p for p in data[lg]["players"]} for lg in ("NFL", "NBA", "CFB") if lg in data}
    for e in list(entries.values()) + list(best.values()):
        if e["status"] != "pending" or start(e) > now:
            continue
        p = players.get(e["lg"], {}).get(e["id"])
        day = start(e).astimezone(ET).date()
        g = None
        if p:
            cols = data[e["lg"]]["cols"]
            for row in p["g"]:
                gm = dict(zip(cols, row))
                gd = dt.date.fromisoformat(gm["date"])
                if abs((gd - day).days) <= 1 and gm["opp"] == e["opp"]:
                    g = gm
                    break
        if g is None:
            # stats usually land by the next morning; after 3 days assume he didn't play
            if now - start(e) > dt.timedelta(days=3):
                e["status"] = "void"
            continue
        v = stat(g, e["market"])
        e["result"] = v
        if v == e["line"]:
            e["status"] = "push"
        elif (v > e["line"]) == (e["side"] == "over"):
            e["status"] = "win"
        else:
            e["status"] = "loss"
        e["graded"] = now.isoformat(timespec="minutes")

    rec["picks"] = sorted(entries.values(), key=lambda e: (e["t"], -e["score"]))
    rec["best"] = sorted(best.values(), key=lambda e: e["t"])
    rec["updated"] = now.isoformat(timespec="minutes")
    rec.setdefault("started", now.astimezone(ET).date().isoformat())
    json.dump(rec, open(OUT, "w"), separators=(",", ":"))
    c = {}
    for e in rec["picks"]:
        c[e["status"]] = c.get(e["status"], 0) + 1
    print(f"wrote {OUT}: {c}")


if __name__ == "__main__":
    main()
