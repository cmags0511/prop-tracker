"""Keep an honest, graded record of the app's Top 10 picks in record.json.

Each run:
  1. Lock in picks. For each league, the app's "Best overall" Top 10 (same rules as the page:
     best play per player across every prop, players ruled out by the daily news check removed)
     is saved for games that haven't started. Until kickoff a pick can still change or drop out
     as lines move; once its game starts it is frozen. So the record is the Top 10 as it stood
     just before each game.
  2. Grade frozen picks against the box score: win, loss, push, or void (player didn't play).

Usage: python record.py [record.json]
"""
import json, sys, datetime as dt
from zoneinfo import ZoneInfo
from picks import stat

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

    # 1. current pre-game Top 10 per league ("Best overall": best play per player across all props)
    for lg in [l for l in ("NFL", "NBA", "CFB") if l in data]:
        pool = {}
        for c in list(picks.get("picks", [])) + [c for k, v in picks.get("byMarket", {}).items() if k.startswith(lg + "|") for c in v]:
            if c["lg"] == lg:
                pool[c["key"]] = c
        top, seen = [], set()
        for c in sorted(pool.values(), key=lambda c: -c["score"]):
            if start(c) <= now or f"{lg}|{c['id']}" in out_players or c["id"] in seen:
                continue
            seen.add(c["id"])
            top.append(c)
            if len(top) == TOP:
                break
        top_ids = {(c["key"], c["t"]) for c in top}
        # drop not-yet-started picks that fell out of the Top 10
        for k, e in list(entries.items()):
            if e["lg"] == lg and e["status"] == "pending" and start(e) > now and k not in top_ids:
                del entries[k]
        for c in top:
            entries[(c["key"], c["t"])] = {
                "key": c["key"], "lg": lg, "id": c["id"], "name": c["name"], "team": c["team"], "opp": c["opp"],
                "home": c["home"], "t": c["t"], "market": c["market"], "label": c["label"], "side": c["side"],
                "line": c["line"], "score": c["score"], "l10": c["l10"], "status": "pending", "result": None,
            }

    # 2. grade picks whose games have started
    players = {lg: {p["id"]: p for p in data[lg]["players"]} for lg in ("NFL", "NBA", "CFB") if lg in data}
    for e in entries.values():
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
    rec["updated"] = now.isoformat(timespec="minutes")
    rec.setdefault("started", now.astimezone(ET).date().isoformat())
    json.dump(rec, open(OUT, "w"), separators=(",", ":"))
    c = {}
    for e in rec["picks"]:
        c[e["status"]] = c.get(e["status"], 0) + 1
    print(f"wrote {OUT}: {c}")


if __name__ == "__main__":
    main()
