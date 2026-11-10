"""One-off backfill: `lock_h` (hours between the last line refresh and kickoff) for Walters games graded before
walters.py started saving it. Reads every committed version of walters.json from git history, so it needs a full
clone (not the workflows' shallow checkout). Only fills games that have no lock_h yet; changes no grade or line.

Usage: python walters_lockage.py [walters.json]   (then commit walters.json)
"""
import json, subprocess, sys, datetime as dt

OUT = sys.argv[1] if len(sys.argv) > 1 else "walters.json"
P = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    revs = subprocess.run(["git", "log", "--format=%H", "--", "walters.json"], capture_output=True, text=True,
                          check=True).stdout.split()
    seen = {}  # game id -> latest build time that still had the game before kickoff with a fresh line
    for h in revs:
        try:
            d = json.loads(subprocess.run(["git", "show", f"{h}:walters.json"], capture_output=True, text=True).stdout)
        except ValueError:
            continue
        if not d.get("built"):
            continue
        b = P(d["built"])
        for g in d.get("games", []):
            if g.get("line") is not None and not g.get("lstale") and b < P(g["t"]):
                if g["id"] not in seen or b > seen[g["id"]]:
                    seen[g["id"]] = b
    data = json.load(open(OUT))
    n = 0
    for g in data["games"]:
        if g.get("status") != "pending" and g.get("lock_h") is None and g["id"] in seen:
            g["lock_h"] = round((P(g["t"]) - seen[g["id"]]).total_seconds() / 3600, 1)
            n += 1
    json.dump(data, open(OUT, "w"), separators=(",", ":"))
    stale = sorted((g["t"][:10], g["away"], g["home"], g["lock_h"]) for g in data["games"] if (g.get("lock_h") or 0) >= 1.5)
    print(f"filled lock_h on {n} games; {len(stale)} locked 1.5h+ before kickoff")
    for s in stale:
        print(" ", *s)


if __name__ == "__main__":
    main()
