"""Keep the history of every DraftKings player-prop line (from lines.json) so the app can chart how a line moved.

line_hist.json: {"updated": ..., "props": {"NFL|<espn id>|<market>": {"g": "CHI @ ATL", "d": kickoff,
                 "o": opening line, "h": [[time, line], ...]}}}
A point is added each time the line changes (time = when ESPN's feed changed it, or when we saw it). The first
point is the opening line (time unknown, so null) when the line had already moved before we first saw it.
Props are dropped a day after their game. Runs right after fetch_lines.py in both workflows.
"""
import datetime as dt
import json
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "line_hist.json"
KEEP_H = 24      # keep a prop this long after kickoff (the app shows its history until the game is graded)
MAX_PTS = 40     # per prop; a line that changes more than this keeps the opening point and the newest ones


def main():
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec="minutes")
    lines = json.load(open("lines.json"))
    try:
        old = json.load(open(OUT)).get("props") or {}
    except (OSError, ValueError):
        old = {}
    props, added, new = {}, 0, 0
    for lg in ("NFL", "NBA", "CFB"):
        for pid, mk in (lines.get(lg) or {}).items():
            for m, r in (mk or {}).items():
                if not isinstance(r, dict) or r.get("line") is None:
                    continue
                k = f"{lg}|{pid}|{m}"
                t = min(r.get("u") or stamp, stamp)  # ESPN sometimes stamps a few hours ahead
                e = old.get(k)
                if e is None or e.get("d") != r.get("d"):  # first time, or a new game for the same player and market
                    h = []
                    if r.get("open") is not None and r["open"] != r["line"]:
                        h.append([None, r["open"]])
                    h.append([t, r["line"]])
                    e = {"g": r.get("g", ""), "d": r.get("d", ""), "o": r.get("open"), "h": h}
                    new += 1
                elif e["h"][-1][1] != r["line"]:
                    # ESPN's stamp can lag or run ahead; never let a point go back in time
                    last_t = max((p[0] for p in e["h"] if p[0]), default=None)
                    e["h"].append([t if (last_t is None or t > last_t) else stamp, r["line"]])
                    if len(e["h"]) > MAX_PTS:
                        e["h"] = e["h"][:1] + e["h"][-(MAX_PTS - 1):]
                    added += 1
                props[k] = e
    # keep props that dropped out of the feed until a day after their game (lines come down at kickoff)
    for k, e in old.items():
        if k in props:
            continue
        try:
            if dt.datetime.fromisoformat(e["d"].replace("Z", "+00:00")) > now - dt.timedelta(hours=KEEP_H):
                props[k] = e
        except (KeyError, ValueError, AttributeError):
            pass
    json.dump({"updated": stamp, "props": props}, open(OUT, "w"), separators=(",", ":"))
    moved = sum(1 for e in props.values() if len(e["h"]) > 1)
    print(f"line history: {len(props)} props ({new} new, {added} line changes this run, {moved} have moved)")


if __name__ == "__main__":
    main()
