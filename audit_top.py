"""Audit the Top 10s exactly as the app shows them, and flag anything that looks botched.

Rebuilds each league's "Best overall" Top 10 (overs, and overs + unders) with the page's rules, then
checks every pick:
  NOT RESEARCHED   no research note on this exact prop
  RESEARCH SAYS X  the research favors the other side
  CAUTION          the research flagged a concern
  LINE GAP         the line is far from his recent average (the book may know something)
  STALE LINE       ESPN hasn't updated the line in over a day
  LINE MOVED?      Kalshi's market centers somewhere else
  CHECK LINE       the research found a different line in current odds pages
  BACKUP           not a starter on the depth chart
  QUESTIONABLE     on the injury report
  BAD PRICE        the sportsbook price needs a higher win rate than the pick's chance
Exit code 1 if any pick has a blocking flag (not researched, research disagrees), so the research run
can fix them before publishing.

Usage: python audit_top.py [--json]
"""
import json, sys, datetime as dt


def load(f, d):
    try:
        return json.load(open(f))
    except Exception:
        return d


def top10(picks, lg, overs, now):
    lk, bk = ("picksOver", "byMarketOver") if overs else ("picks", "byMarket")
    pool = {}
    for c in list(picks.get(lk, [])) + [c for k, v in picks.get(bk, {}).items() if k.startswith(lg + "|") for c in v]:
        if c["lg"] == lg and dt.datetime.fromisoformat(c["t"]) > now and (not overs or c["side"] == "over"):
            pool[c["key"]] = c
    out, seen, per = [], set(), {}
    for c in sorted(pool.values(), key=lambda c: -c["score"]):
        if c["id"] in seen or per.get(c["market"], 0) >= 3:
            continue
        seen.add(c["id"])
        per[c["market"]] = per.get(c["market"], 0) + 1
        out.append(c)
        if len(out) == 10:
            break
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    picks = load("picks.json", {})
    notes = (load("notes.json", {}) or {}).get("notes", {})
    blocking, report = 0, []
    for lg in ("NFL", "NBA", "CFB"):
        for overs in (True, False):
            lst = top10(picks, lg, overs, now)
            if not lst:
                continue
            print(f"== {lg} Top 10 {'overs' if overs else 'overs + unders'}")
            for i, c in enumerate(lst):
                n = notes.get(c["key"]) or {}
                flags = []
                if not n:
                    flags.append("NOT RESEARCHED")
                elif n.get("side") in ("over", "under") and n["side"] != c["side"]:
                    flags.append(f"RESEARCH SAYS {n['side'].upper()}")
                if n.get("flag") == "caution":
                    flags.append("CAUTION")
                if (c.get("gap") or 0) > .25:
                    flags.append("LINE GAP")
                if (c.get("age_h") or 0) > 24:
                    flags.append("STALE LINE")
                if c.get("moved"):
                    flags.append(f"LINE MOVED? (Kalshi ~{c['moved']})")
                if n.get("line_now") is not None and abs(float(n["line_now"]) - c["line"]) >= max(1, .05 * c["line"]):
                    flags.append(f"CHECK LINE (odds pages: {n['line_now']})")
                if c.get("role") == "backup":
                    flags.append("BACKUP")
                if c.get("status"):
                    flags.append(c["status"].upper())
                if c.get("break_even") and c.get("prob") and c["prob"] < c["break_even"]:
                    flags.append("BAD PRICE")
                block = any(f.startswith(("NOT RESEARCHED", "RESEARCH SAYS")) for f in flags)
                blocking += block
                report.append({"lg": lg, "overs": overs, "rank": i + 1, "key": c["key"], "name": c["name"],
                               "pick": f"{c['side']} {c['line']} {c['label']}", "flags": flags, "blocking": block})
                print(f"{i + 1:2}. {'!!' if block else '  '} {c['name']:24} {c['side']:5} {c['line']:6} {c['label']:20} "
                      f"{', '.join(flags) or 'ok'}   [{c['key']}]")
    if "--json" in sys.argv:
        json.dump(report, open("research/audit.json", "w"), indent=1)
    print(f"{blocking} pick(s) need fixing before publishing" if blocking else "all Top 10 picks are researched and agree with the research")
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()
