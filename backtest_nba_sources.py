"""NBA signal backtest (Oct 28): box-score signals (starter role, team and opponent pace, recent scoring margin, rest,
opponent 3-point volume, minutes held by teammates who sit out today) and pbpstats.com season-to-date player profiles
(usage, assisted share, shot-zone mix, net rating per minute) against synthetic player props (line = weighted average of his
last 10 games; points, rebounds, assists, threes). Each feature is added alone to the base (recent form, season mean, hit rate,
opponent allowed, minutes trend); train 2023-25, test 2026 (the 2025-26 season). Reports log-loss gain, a t-statistic and the
top-20% hit rate. Result (Oct 28): box-score set 7 of 46 tests passed (about 2 expected): teammates out (already in the app),
opponent pace for rebounds, team margin for points/assists, all small. pbpstats set 3 of 40 (about 2 expected): noise.
Usage: python backtest_nba_sources.py [data_dir]  (downloads about 80 MB plus 20 pbpstats calls)
"""
import sys, os, urllib.request
D = (sys.argv[1] if len(sys.argv) > 1 else "backtest_data").rstrip("/") + "/"
os.makedirs(D, exist_ok=True)


def fetch(url, name, tries=3):
    """download once into D (plain requests only: no spoofed browser headers)"""
    f = D + name
    if os.path.exists(f) and os.path.getsize(f) > 100:
        return f
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "prop-tracker-backtest"}), timeout=180) as r, open(f, "wb") as o:
                o.write(r.read())
            return f
        except Exception as e:
            err = e
    print("could not download", url, err)
    return None


import pandas as pd, numpy as np, glob, re, warnings
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, json, re, warnings
warnings.filterwarnings("ignore")
SV = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
for y in (2023, 2024, 2025, 2026):
    fetch(f"{SV}espn_nba_player_boxscores/player_box_{y}.csv", f"nba_pb{y}.csv")
b=pd.concat([pd.read_csv(f"{D}nba_pb{y}.csv",low_memory=False) for y in (2023,2024,2025,2026)])
b=b[b.season_type==2] if b.season_type.dtype!=object else b[b.season_type.str.contains("egular",na=False)|(b.season_type=="2")]
print("box rows",len(b), b.season_type.unique()[:3])
b["dnp"]=b.did_not_play.astype(str).str.lower().isin(["true","1"])
b["min"]=pd.to_numeric(b.minutes,errors="coerce").fillna(0)
for c in ["points","rebounds","assists","three_point_field_goals_made","three_point_field_goals_attempted","field_goals_attempted","free_throws_attempted","offensive_rebounds","turnovers","team_score","opponent_team_score"]:
    b[c]=pd.to_numeric(b[c],errors="coerce")
b["date"]=pd.to_datetime(b.game_date)
b["starter_f"]=b.starter.astype(str).str.lower().isin(["true","1"]).astype(float)
b=b.sort_values(["athlete_id","date"]).reset_index(drop=True)
# team-game table
tg=b[~b.dnp].groupby(["game_id","team_id"]).agg(date=("date","first"),season=("season","first"),fga=("field_goals_attempted","sum"),fta=("free_throws_attempted","sum"),
   orb=("offensive_rebounds","sum"),tov=("turnovers","sum"),f3a=("three_point_field_goals_attempted","sum"),pts=("team_score","first"),opts=("opponent_team_score","first"),opp=("opponent_team_id","first")).reset_index()
tg["poss"]=tg.fga+.44*tg.fta-tg.orb+tg.tov; tg["margin"]=tg.pts-tg.opts
tg=tg.sort_values(["team_id","date"])
for c in ["poss","margin"]:
    tg["own_"+c]=tg.groupby("team_id")[c].transform(lambda x:x.shift(1).rolling(5,min_periods=3).mean())
tg["prev_absmargin"]=tg.groupby("team_id").margin.shift(1).abs()
tg["rest"]=tg.groupby("team_id").date.diff().dt.days.clip(upper=5)
# what each defense allowed (opponent three-point attempts and possessions faced)
al=tg[["game_id","opp","f3a","poss","date"]].rename(columns={"opp":"team_id"}).sort_values(["team_id","date"])
al["opp_f3a_allowed"]=al.groupby("team_id").f3a.transform(lambda x:x.shift(1).rolling(5,min_periods=3).mean())
tgi=tg.set_index(["game_id","team_id"]); ali=al.set_index(["game_id","team_id"])
MK={"points":("pts",10),"rebounds":("reb",4),"assists":("ast",3),"three_point_field_goals_made":("fg3m",1.5)}
rows=[]
for pid,g in b.groupby("athlete_id"):
    g=g[~g.dnp].reset_index(drop=True)
    if len(g)<12: continue
    mins=g["min"].values; st=g.starter_f.values
    for col,(m,thr) in MK.items():
        v=g[col].values.astype(float)
        for i in range(10,len(g)):
            if mins[i]<=0: continue
            h=v[i-10:i][::-1]; w=.9**np.arange(10); avg=(h*w).sum()/w.sum()
            if avg<thr or mins[i-10:i].mean()<18: continue
            line=np.round(avg-.5)+.5
            sd=max(h.std(),1e-6); s=g.season.iloc[i]
            sea=v[:i][g.season.values[:i]==s]
            rows.append(dict(pid=pid,m=m,season=s,gid=g.game_id.iloc[i],tid=g.team_id.iloc[i],oid=g.opponent_team_id.iloc[i],date=g.date.iloc[i],line=line,y=float(v[i]>line),
               z=(h[:3].mean()-line)/sd,mu=((sea.mean() if len(sea)>=3 else avg)-line)/sd,pf=(h[:5]>line).mean()-.5,
               mn=(mins[i-3:i].mean()-mins[i-10:i].mean())/max(mins[i-10:i].mean(),1),
               f_starter=st[i-5:i].mean(),f_min10=mins[i-10:i].mean()))
r=pd.DataFrame(rows); print("rows",len(r),r.groupby("m").size().to_dict())
# opponent defense allowed (stat) previous 5, league-standardised
for col,(m,thr) in MK.items():
    a=b[~b.dnp].groupby(["opponent_team_id","game_id","date","season"])[col].sum().reset_index().sort_values(["opponent_team_id","date"])
    a["p5"]=a.groupby("opponent_team_id")[col].transform(lambda x:x.shift(1).rolling(5,min_periods=3).mean())
    a["od"]=(a.p5-a.groupby("season")[col].transform("mean"))/a[col].std()
    k=a.set_index(["opponent_team_id","game_id"]).od
    idx=r.m==m; r.loc[idx,"od"]=[k.get((o,g_),np.nan) for o,g_ in zip(r.oid[idx],r.gid[idx])]
r["od"]=r.od.fillna(0)
# new features
def look(df,col,keys): 
    k=df[col]; return [k.get(x,np.nan) for x in keys]
r["own_pace"]=look(tgi,"own_poss",list(zip(r.gid,r.tid)))
opp_pace=look(tgi,"own_poss",list(zip(r.gid,r.oid))); r["opp_pace"]=opp_pace
r["pace_sum"]=r.own_pace+r.opp_pace
r["own_margin5"]=look(tgi,"own_margin",list(zip(r.gid,r.tid)))
r["opp_margin5"]=look(tgi,"own_margin",list(zip(r.gid,r.oid)))
r["mismatch"]=(r.own_margin5-r.opp_margin5).abs()
r["prev_absmargin"]=look(tgi,"prev_absmargin",list(zip(r.gid,r.tid)))
r["rest"]=look(tgi,"rest",list(zip(r.gid,r.tid)))
r["opp_rest"]=look(tgi,"rest",list(zip(r.gid,r.oid)))
r["opp_f3a_allowed"]=look(ali,"opp_f3a_allowed",list(zip(r.gid,r.oid)))
# teammates out today (ESPN lists them as did-not-play on the box score): their recent minutes, summed
b["m10_all"] = b.groupby("athlete_id")["min"].transform(lambda x: x.where(~b.loc[x.index, "dnp"]).shift(1).rolling(10, min_periods=5).mean())
out = b[b.dnp & (b.m10_all >= 18)].groupby(["game_id", "team_id"]).m10_all.sum()
r["tm_out_min"]=[out.get((g_,t_),0.0) for g_,t_ in zip(r.gid,r.tid)]


def norm(n):
    t = re.sub(r"[^a-z ]", "", str(n).lower()).split()
    while len(t) > 2 and t[-1] in ("jr", "sr", "ii", "iii", "iv", "v"):
        t = t[:-1]
    return "".join(t)


# --- pbpstats.com season-to-date player totals at the start of each month (free public API), joined by name
import time
SEAS = {2023: ("2022-23", "2022-10-15"), 2024: ("2023-24", "2023-10-15"), 2025: ("2024-25", "2024-10-15"), 2026: ("2025-26", "2025-10-15")}
feat = {}
for y, (s, start) in SEAS.items():
    for md in ("12-01", "01-01", "02-01", "03-01", "04-01"):
        yr = y - 1 if md == "12-01" else y
        f = fetch(f"https://api.pbpstats.com/get-totals/nba?Season={s}&SeasonType=Regular%20Season&Type=Player&StartDate={start}&EndDate={yr}-{md}", f"pbp_{y}_{md}.json")
        if not f:
            continue
        j = json.load(open(f))
        d = pd.DataFrame(j["multi_row_table_data"] if isinstance(j, dict) else j)
        m = d.Minutes.clip(lower=1); fga = (d.FG2A + d.FG3A).clip(lower=1)
        d["usg"] = fga / m
        d["ast_share_2"] = d.PtsAssisted2s / (2 * d.FG2M).clip(lower=1)
        d["ast_share_3"] = d.PtsAssisted3s / (3 * d.FG3M).clip(lower=1)
        d["rim_rate"] = d.AtRimFGA / fga; d["three_rate"] = d.FG3A / fga
        d["corner3_rate"] = d.Corner3FGA / d.FG3A.clip(lower=1)
        d["midrange_rate"] = (d.ShortMidRangeFGA + d.LongMidRangeFGA) / fga
        d["pm_per_min"] = d.PlusMinus / m; d["pts_per_min"] = d.Points / m; d["poss_per_min"] = d.OffPoss / m
        d["nm"] = d.Name.map(norm); d = d[d.GamesPlayed >= 12]
        feat[(y, pd.Timestamp(f"{yr}-{md}"))] = d.set_index("nm")
        time.sleep(1)
PBC = ["usg", "ast_share_2", "ast_share_3", "rim_rate", "three_rate", "corner3_rate", "midrange_rate", "pm_per_min", "pts_per_min", "poss_per_min"]
bx = pd.concat([pd.read_csv(f"{D}nba_pb{y}.csv", usecols=["athlete_id", "athlete_display_name"], low_memory=False) for y in (2023, 2024, 2025, 2026)]).drop_duplicates("athlete_id")
r["nm"] = r.pid.map(dict(zip(bx.athlete_id, bx.athlete_display_name.map(norm))))
for c in PBC:
    r["pb_" + c] = np.nan
for y in r.season.unique():
    ks = sorted([k for k in feat if k[0] == y], key=lambda k: k[1])
    for i, k in enumerate(ks):
        nxt = ks[i + 1][1] if i + 1 < len(ks) else pd.Timestamp("2100-01-01")
        idx = (r.season == y) & (r.date >= k[1]) & (r.date < nxt)
        for c in PBC:
            r.loc[idx, "pb_" + c] = r.loc[idx, "nm"].map(feat[k][c]).values

BASE=["z","mu","pf","od","mn"]
def logit(X,y,lam=1.0,it=40):
    X=np.column_stack([np.ones(len(X)),X]); b=np.zeros(X.shape[1])
    for _ in range(it):
        p=1/(1+np.exp(-X@b)); W=p*(1-p); H=X.T@(X*W[:,None])+lam*np.eye(len(b)); H[0,0]-=lam
        b+=np.linalg.solve(H,X.T@(y-p)-lam*np.r_[0,b[1:]])
    return b
pred=lambda X,b:1/(1+np.exp(-np.column_stack([np.ones(len(X)),X])@b))
def rll(p,y):
    p=np.clip(p,1e-6,1-1e-6); return y*np.log(p)+(1-y)*np.log(1-p)
def top(p,y,q=.2):
    c=np.abs(p-.5); m=c>=np.quantile(c,1-q); return np.mean((p[m]>=.5)==(y[m]==1)),m.sum()
feats=["f_starter","own_pace","opp_pace","pace_sum","own_margin5","opp_margin5","mismatch","prev_absmargin","rest","opp_rest","opp_f3a_allowed","tm_out_min"]+["pb_"+c for c in PBC]
applies=lambda f,m:(f!="opp_f3a_allowed" or m in("fg3m","pts"))
MS=["pts","reb","ast","fg3m"]
out=[]
# overall base calibration check
for m in MS:
    s=r[r.m==m]; tr,te=s[s.season<=2025],s[s.season>=2026]
    b=logit(tr[BASE].values,tr.y.values); p=pred(te[BASE].values,b)
    print(f"base {m:6s} train n={len(tr)} test n={len(te)} test over-rate {te.y.mean():.3f}  base top20 hit {top(p,te.y.values)[0]:.3f}")
for m in MS:
    s=r[r.m==m]
    for f in feats:
        if not applies(f,m): continue
        d=s.dropna(subset=[f]); tr,te=d[d.season<=2025],d[d.season>=2026]
        if len(tr)<400 or len(te)<250: continue
        mu,sd=tr[f].mean(),tr[f].std() or 1
        ztr=((tr[f]-mu)/sd).clip(-3,3).values; zte=((te[f]-mu)/sd).clip(-3,3).values
        ytr,yte=tr.y.values,te.y.values
        b0=logit(tr[BASE].values,ytr); b1=logit(np.column_stack([tr[BASE].values,ztr]),ytr)
        p0=pred(te[BASE].values,b0); p1=pred(np.column_stack([te[BASE].values,zte]),b1)
        dl=rll(p1,yte)-rll(p0,yte); t=dl.mean()/(dl.std()/np.sqrt(len(dl))+1e-12)
        bt=logit(np.column_stack([te[BASE].values,zte]),yte)
        h0,_=top(p0,yte); h1,n=top(p1,yte)
        out.append((m,f,len(te),b1[-1],bt[-1],dl.mean()*1e4,t,h0,h1))
S=pd.DataFrame(out,columns=["m","feat","n_test","coef_train","coef_test","dLL_e4","t","top0","top1"])
S["same_sign"]=np.sign(S.coef_train)==np.sign(S.coef_test)
S.to_csv(""+D+"nba_summary.csv",index=False)
print(f"\ntested {len(S)} feature/market combos")
print("positive dLL:",(S.dLL_e4>0).sum(),"| positive & same sign & |t|>=2:",((S.dLL_e4>0)&S.same_sign&(S.t.abs()>=2)).sum())
print("expected by chance at |t|>=2 (~5%):",round(len(S)*.05,1))
print(S.sort_values("t",ascending=False).head(14).to_string(index=False,float_format=lambda x:f"{x:.3f}"))
print("\nworst:"); print(S.sort_values("t").head(5).to_string(index=False,float_format=lambda x:f"{x:.3f}"))
