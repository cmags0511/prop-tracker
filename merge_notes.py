"""Merge the per-game research (research/out/<game id>.json) and the lead summary (research/lead.json)
into notes.json, checking every field so one sloppy write-up can't break the picks. See RESEARCH.md.

Per-game file:
  {"game": "<packet id>", "summary": "<2-3 sentences: the game's storyline>", "sources": [urls],
   "notes": {"<slate key>": {"side": "over|under", "flag": "out|caution|support|neutral", "adj": -2..2,
             "conf": "low|medium|high", "note": "<one sentence>",
             "detail": {"availability": "...", "role": "...", "matchup": "...", "script": "...",
                        "conditions": "...", "market": "...", "experts": "..."},
             "sources": [urls]}},
   "best_candidate": {"key": "...", "side": "over", "why": "...", "sources": [urls]} or null}
College file (research/out/CFB-week.json) may also carry the published prop lines it researched:
   "lines": [{"key": "CFB|<player id>|<market>", "line": 245.5, "book": "FanDuel", "source": "<url>"}]
Lead file: {"summary": "<1-2 sentences for the whole slate>", "best": {"key", "side", "why", "sources"}}

Notes from the previous run are kept for games this run didn't cover, if their game hasn't started.
Usage: python merge_notes.py
"""
import glob, json, sys, datetime as dt

FLAGS = {"out", "caution", "support", "neutral"}
DETAIL = ("availability", "role", "matchup", "script", "conditions", "market", "experts")


def load(f, d=None):
    try:
        return json.load(open(f))
    except Exception as e:
        if d is None:
            print(f"skipping {f}: {e}")
        return d


def urls(v, n=6):
    return [u for u in (v or []) if isinstance(u, str) and u.startswith("http")][:n]


def txt(v, n):
    v = " ".join(str(v or "").split())
    return v if len(v) <= n else v[: n - 1].rsplit(" ", 1)[0] + "…"


def clean_note(n):
    side = n.get("side") if n.get("side") in ("over", "under") else None
    try:
        adj = max(-2, min(2, int(round(float(n.get("adj") or 0)))))
    except (TypeError, ValueError):
        adj = 0
    out = {"side": side, "flag": n.get("flag") if n.get("flag") in FLAGS else "neutral", "adj": adj,
           "conf": n.get("conf") if n.get("conf") in ("low", "medium", "high") else "medium",
           "note": txt(n.get("note"), 320), "sources": urls(n.get("sources"))}
    det = {k: txt((n.get("detail") or {}).get(k), 300) for k in DETAIL if (n.get("detail") or {}).get(k)}
    if det:
        out["detail"] = det
    if not out["side"]:
        out.pop("side")
    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    slate = {p["key"]: p for p in load("slate.json", {"props": []})["props"]}
    # college players (no DraftKings lines in the feed): allow notes on any of their props, with a researched line
    cfb = load("cfb_data.json", {}) or {}
    cfb_team = {p["id"]: p["t"] for p in cfb.get("players", [])}
    cfb_next = {}
    for u in cfb.get("upcoming", []):
        t = dt.datetime.fromisoformat(u[0])
        if t > now:
            for tm, opp in ((u[1], u[2]), (u[2], u[1])):
                if tm not in cfb_next or t < cfb_next[tm][0]:
                    cfb_next[tm] = (t, opp)
    CFB_M = {"pyd", "cmp", "att", "ptd", "ryd", "car", "rec", "recyd", "rry"}
    cfb_lines = {}
    # anytime-TD keys the packets offered (no DraftKings line, so they aren't on the slate)
    td_ok = {c["key"] for f in glob.glob("research/packets/*.json") for c in (load(f, {}) or {}).get("td_candidates", [])}

    def cfb_key(k):
        parts = k.split("|")
        return len(parts) == 3 and parts[0] == "CFB" and parts[1] in cfb_team and parts[2] in CFB_M and cfb_team[parts[1]] in cfb_next
    old = load("notes.json", {}) or {}
    lead = load("research/lead.json", {}) or {}
    notes, games, bad = {}, {}, []
    covered = set()
    for f in sorted(glob.glob("research/out/*.json")):
        g = load(f)
        if not isinstance(g, dict):
            continue
        gid = g.get("game") or f.split("/")[-1][:-5]
        games[gid] = {"summary": txt(g.get("summary"), 600), "sources": urls(g.get("sources"), 8)}
        for ln in g.get("lines") or []:
            try:
                k, line = ln["key"], float(ln["line"])
            except (KeyError, TypeError, ValueError):
                bad.append(str(ln)[:40])
                continue
            if not cfb_key(k) or line <= 0 or line % 1 not in (0, .5):
                bad.append(k)
                continue
            t, opp = cfb_next[cfb_team[k.split("|")[1]]]
            cfb_lines[k] = {"line": line, "book": txt(ln.get("book") or "consensus", 40), "t": t.isoformat(),
                            "opp": opp, "source": (urls([ln.get("source")]) or [None])[0]}
        for k, n in (g.get("notes") or {}).items():
            if k.startswith("CFB|") and cfb_key(k) and isinstance(n, dict):
                notes[k] = clean_note(n)
                continue
            if k in td_ok and isinstance(n, dict):
                notes[k] = clean_note(n)
                continue
            if k not in slate or not isinstance(n, dict):
                bad.append(k)
                continue
            notes[k] = clean_note(n)
            covered.add((slate[k]["team"], slate[k]["t"]))
            covered.add((slate[k]["opp"], slate[k]["t"]))
    # keep last run's notes for games nobody re-researched this time (and that haven't started)
    kept = 0
    for k, v in (old.get("cfb_lines") or {}).items():  # keep last run's college lines until kickoff
        if k not in cfb_lines and not any(f.endswith("CFB-week.json") for f in glob.glob("research/out/*.json")) \
                and dt.datetime.fromisoformat(v["t"]) > now:
            cfb_lines[k] = v
            if k in (old.get("notes") or {}):
                notes.setdefault(k, old["notes"][k])
    for k, n in (old.get("notes") or {}).items():
        p = slate.get(k)
        if k in notes or not p or (p["team"], p["t"]) in covered or dt.datetime.fromisoformat(p["t"]) <= now:
            continue
        notes[k] = n
        kept += 1
    for gid, gv in (old.get("games") or {}).items():
        if gid not in games:
            try:
                if dt.datetime.strptime(gid.rsplit("-", 1)[1] + str(now.year), "%m%d%Y").date() >= now.date():
                    games[gid] = gv
            except Exception:
                pass
    best = None
    b = lead.get("best") or {}
    if (b.get("key") in slate or b.get("key") in cfb_lines) and b.get("side") in ("over", "under"):
        n = notes.get(b["key"])
        if not n or n.get("side") != b["side"]:
            print(f"best bet {b['key']} has no matching note; adding one at +2")
            notes[b["key"]] = clean_note({"side": b["side"], "flag": "support", "adj": 2, "conf": "high",
                                          "note": b.get("why", ""), "sources": b.get("sources")})
        best = {"key": b["key"], "side": b["side"], "why": txt(b.get("why"), 700), "sources": urls(b.get("sources"))}
    elif b:
        print(f"best bet ignored: {b.get('key')} not on the slate or no side")
    out = {"updated": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
           "summary": txt(lead.get("summary") or old.get("summary"), 500), "notes": notes, "games": games,
           "cfb_lines": cfb_lines}  # every college line collected, researched or not; the app ranks them all
    if best:
        out["best"] = best
    json.dump(out, open("notes.json", "w"), indent=1)
    sides = {s: sum(1 for n in notes.values() if n.get("side") == s) for s in ("over", "under")}
    print(f"notes.json: {len(notes)} notes ({sides['over']} over, {sides['under']} under; {kept} kept from last run), "
          f"{len(games)} game write-ups, {len(out['cfb_lines'])} college lines, best bet {'set' if best else 'none'}"
          + (f"; dropped {len(bad)} notes with unknown keys: {bad[:5]}" if bad else ""))


if __name__ == "__main__":
    main()
