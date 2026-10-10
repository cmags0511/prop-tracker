"""Pull player-prop prices from Kalshi's prediction markets into markets.json.

Kalshi lists "ladder" markets for NFL and NBA players, e.g. "Dak Prescott: 250+ passing yards", each
priced from $0.01 to $0.99. A price is the crowd's probability: 0.57 = a 57% chance. Reading the ladder
at DraftKings' line gives the market's probability of the over at that exact number.

Kalshi's market data API is public and free (no account or key). Prices are bid/ask quotes; we use
the midpoint and skip markets where the bid/ask spread is too wide to mean much.

Output, per league and player id (same ids as props_data.json / cfb_data.json):
  {"NFL": {"<id>": {"pyd": {"g": "<kalshi event>", "t": "<close time>", "k": [[strike, prob, spread], ...]}}}}
where strike s means "more than s" (Kalshi's "250+" is s = 249.5).

Usage: python fetch_markets.py [markets.json]
"""
import json, re, sys, time, unicodedata, datetime as dt
import urllib.request, urllib.parse

OUT = sys.argv[1] if len(sys.argv) > 1 else "markets.json"
API = "https://api.elections.kalshi.com/trade-api/v2"
H = {"User-Agent": "Mozilla/5.0 (prop-tracker)", "Accept": "application/json"}
SERIES = {
    "NFL": {"KXNFLPASSYDS": "pyd", "KXNFLPASSCOMP": "cmp", "KXNFLPASSTDS": "ptd", "KXNFLRSHYDS": "ryd",
            "KXNFLRSHATT": "car", "KXNFLRECYDS": "recyd", "KXNFLREC": "rec", "KXNFLRRYDS": "rry",
            "KXNFLTD": "td", "KXNFLSACK": "sck"},
    "NBA": {"KXNBAPTS": "pts", "KXNBAREB": "reb", "KXNBAAST": "ast", "KXNBA3PT": "3pm", "KXNBAPRA": "pra"},
}
# game-winner markets (one market per team): the crowd's chance each side wins
GAME_SERIES = {"NFL": "KXNFLGAME", "CFB": "KXNCAAFGAME", "NBA": "KXNBAGAME"}
MAX_SPREAD = .15  # quotes wider than 15 cents are too loose to read a probability from
# Kalshi team codes that differ from the app's (nflverse) codes
TEAM_FIX = {"NFL": {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"}, "NBA": {"GSW": "GS", "NYK": "NY", "SAS": "SA", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH"}}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=40) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def norm(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'\-]", " ", n)
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", n)
    return " ".join(n.split())


def download():
    """raw open markets per series"""
    raw = {}
    for lg, series in SERIES.items():
        for s in series:
            out, cursor = [], ""
            for _ in range(10):
                q = {"series_ticker": s, "status": "open", "limit": 1000}
                if cursor:
                    q["cursor"] = cursor
                d = get(f"{API}/markets?" + urllib.parse.urlencode(q))
                out += d.get("markets", [])
                cursor = d.get("cursor") or ""
                if not cursor:
                    break
                time.sleep(.15)
            raw[s] = out
            time.sleep(.15)
    return raw


def download_series(s):
    out, cursor = [], ""
    for _ in range(10):
        q = {"series_ticker": s, "status": "open", "limit": 1000}
        if cursor:
            q["cursor"] = cursor
        d = get(f"{API}/markets?" + urllib.parse.urlencode(q))
        out += d.get("markets", [])
        cursor = d.get("cursor") or ""
        if not cursor:
            break
        time.sleep(.15)
    return out


def build_games(raw_games, data):
    """{"NFL": {"AWAY@HOME|YYYY-MM-DD": {"away": p, "home": p, "spread": worst bid/ask gap}}} for the app's upcoming games.
    Kalshi's event code is the date plus both team codes (e.g. 26OCT11CINMIA), and each team's market ends
    with its code."""
    out = {}
    for lg, s in GAME_SERIES.items():
        meta = data.get(lg) or {}
        ups = meta.get("upcoming") or []
        fix = TEAM_FIX.get(lg, {})
        back = {v: k for k, v in fix.items()}
        by_event = {}
        for m in raw_games.get(s, []):
            parts = (m.get("ticker") or "").split("-")
            if len(parts) < 3:
                continue
            by_event.setdefault(parts[1], {})[parts[2]] = m
        res = {}
        for u in ups:
            t = dt.datetime.fromisoformat(u[0])
            et = t.astimezone(dt.timezone(dt.timedelta(hours=-4)))
            code = f"{et:%y}{et.strftime('%b').upper()}{et:%d}"
            away, home = u[1], u[2]
            ka, kh = back.get(away, away), back.get(home, home)
            ev = by_event.get(code + ka + kh) or by_event.get(code + kh + ka)
            if not ev or ka not in ev or kh not in ev:
                continue
            mids, gaps = {}, []
            for side, k in (("away", ka), ("home", kh)):
                bid, ask = num(ev[k].get("yes_bid_dollars")), num(ev[k].get("yes_ask_dollars"))
                if bid is None or ask is None or ask <= 0:
                    break
                mids[side] = (bid + ask) / 2
                gaps.append(ask - bid)
            if len(mids) != 2 or max(gaps) > .2 or sum(mids.values()) <= 0:
                continue
            tot = mids["away"] + mids["home"]
            res[f"{away}@{home}|{t.astimezone(dt.timezone.utc):%Y-%m-%d}"] = {
                "away": round(mids["away"] / tot, 3), "home": round(mids["home"] / tot, 3), "spread": round(max(gaps), 3)}
        out[lg] = res
    return out


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(raw, data):
    """match Kalshi players to the app's players and collect each ladder"""
    out = {"NFL": {}, "NBA": {}}
    stats = {}
    for lg, series in SERIES.items():
        if lg not in data:
            continue
        by_name = {}
        for p in data[lg]["players"]:
            by_name.setdefault(norm(p["n"]), []).append(p)
        fix = TEAM_FIX.get(lg, {})
        for s, mid in series.items():
            hit = miss = 0
            for m in raw.get(s, []):
                title = m.get("title") or ""
                mm = re.match(r"^(.+?):\s*\d", title)
                strike = num(m.get("floor_strike"))
                if not mm or strike is None or m.get("strike_type") != "greater":
                    continue
                bid, ask = num(m.get("yes_bid_dollars")), num(m.get("yes_ask_dollars"))
                if bid is None or ask is None or ask <= 0 or bid <= 0 and ask >= .99:
                    continue
                spread = ask - bid
                if spread > MAX_SPREAD:
                    continue
                cands = by_name.get(norm(mm.group(1)), [])
                if len(cands) > 1:
                    # several players share the name: the market ticker's player part starts with his team
                    # code (e.g. "...-DALDPRESCOTT4-375"), so keep the one whose team matches
                    parts = (m.get("ticker") or "").split("-")
                    seg = parts[2] if len(parts) > 2 else ""
                    cands = [p for p in cands if any(seg.startswith(k) and fix.get(k, k) == p["t"]
                                                     for k in {p["t"], *[k for k, v in fix.items() if v == p["t"]]})]
                if len(cands) != 1:
                    miss += 1
                    continue
                p = cands[0]
                rec = out[lg].setdefault(p["id"], {}).setdefault(mid, {"g": m.get("event_ticker", ""), "t": m.get("close_time", ""), "k": []})
                if rec["g"] != m.get("event_ticker", ""):
                    # keep only the soonest game's ladder
                    if (m.get("close_time") or "") >= rec["t"]:
                        continue
                    rec.update(g=m.get("event_ticker", ""), t=m.get("close_time", ""), k=[])
                rec["k"].append([strike, round((bid + ask) / 2, 3), round(spread, 3)])
                hit += 1
            stats[s] = (hit, miss)
    for lg in out:
        for pid, mk in out[lg].items():
            for mid, rec in mk.items():
                k = sorted(rec["k"])
                # a ladder must fall as the bar rises; smooth out quotes that don't
                run = 1.0
                for row in k:
                    row[1] = run = min(run, row[1])
                rec["k"] = k
    return out, stats


def main():
    now = dt.datetime.now(dt.timezone.utc)
    try:
        old = json.load(open(OUT))
    except Exception:
        old = {}
    data = json.load(open("props_data.json"))
    try:
        raw = download()
    except Exception as e:
        print(f"Kalshi unreachable ({e}); keeping previous markets.json")
        return
    mk, stats = build(raw, data)
    try:
        cfb = json.load(open("cfb_data.json"))
        gdata = {"NFL": data.get("NFL"), "NBA": data.get("NBA"), "CFB": cfb}
        games = build_games({s: download_series(s) for s in GAME_SERIES.values()}, gdata)
    except Exception as e:
        print(f"game markets failed ({e})")
        games = old.get("games", {})
    if not any(mk.values()) and old:
        print("no Kalshi prop markets matched; keeping previous markets.json")
        return
    json.dump({"fetched": now.isoformat(timespec="minutes"), "source": "Kalshi", **mk, "games": games}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: " + ", ".join(f"{lg} {len(v)} players" for lg, v in mk.items()) + " | "
          + ", ".join(f"{s} {h}/{h + m}" for s, (h, m) in stats.items())
          + " | game odds: " + ", ".join(f"{lg} {len(v)}" for lg, v in games.items()))


if __name__ == "__main__":
    main()
