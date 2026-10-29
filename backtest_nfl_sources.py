"""NFL signal backtest (Oct 28): do nflverse's FTN play charting (offense and the defense it faces), Pro Football Reference
advanced stats, referee crews and the injury/practice report predict prop results beyond recent form?
Rows = every player game 2023-26 for 7 prop types; synthetic line = weighted average of his last 10 games (nearest x.5),
y = went over. Base features: recent form z, season mean, hit rate vs the line, opponent allowed (5 games). Each new
feature is added alone; train 2023-24, test 2025-26 (walk-forward: features use only earlier games). Reports the
out-of-sample log-loss gain, a t-statistic on it, and the hit rate of the most confident 20% of picks.
Result (Oct 28): 258 feature/market tests, 4 with a positive gain, the same sign in train and test and |t| >= 2 (about 13
expected by chance): nothing beats noise; no weight. Injury/practice flags: players listed hit overs 3-8 points less often,
but the gain over the base features is below the bar. Usage: python backtest_nfl_sources.py [data_dir]  (downloads about 150 MB)
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
NV = "https://github.com/nflverse/nflverse-data/releases/download/"
YRS = [2022, 2023, 2024, 2025, 2026]
for y in YRS:
    fetch(f"{NV}stats_player/stats_player_week_{y}.csv", f"stats_player_stats_player_week_{y}.csv")
    fetch(f"{NV}ftn_charting/ftn_charting_{y}.csv", f"ftn_charting_ftn_charting_{y}.csv")
    fetch(f"{NV}pbp/play_by_play_{y}.csv.gz", f"pbp_{y}.csv.gz")
    fetch(f"{NV}injuries/injuries_{y}.csv", f"inj_{y}.csv")
    for k in ("pass", "rec", "rush"):
        fetch(f"{NV}pfr_advstats/advstats_week_{k}_{y}.csv", f"pfr_advstats_advstats_week_{k}_{y}.csv")
fetch(NV + "schedules/games.csv", "games.csv")
fetch(NV + "officials/officials.csv", "off.csv")
st=pd.concat([pd.read_csv(f"{D}stats_player_stats_player_week_{y}.csv",low_memory=False) for y in YRS])
st=st[st.season_type=="REG"].copy()
st=st.rename(columns={"passing_yards":"pyd","completions":"cmp","attempts":"att","rushing_yards":"ryd","carries":"car","receptions":"rec","receiving_yards":"recyd"})
st=st.sort_values(["player_id","season","week"]).reset_index(drop=True)
MK={"pyd":("QB",150),"cmp":("QB",12),"att":("QB",20),"ryd":("RB",25),"car":("RB",6),"rec":("WR TE RB",2.5),"recyd":("WR TE",25)}
# --- rows
rows=[]
for pid,g in st.groupby("player_id"):
    g=g.reset_index(drop=True)
    for m,(pos,thr) in MK.items():
        if g.position.iloc[0] not in pos.split(): continue
        v=g[m].values.astype(float)
        for i in range(10,len(g)):   # need 10 prior games
            h=v[i-10:i][::-1]; w=.9**np.arange(10); avg=(h*w).sum()/w.sum()
            if avg<thr: continue
            line=np.round(avg-.5)+.5
            if v[i]==line: continue
            sd=max(h.std(),1e-6); s=g.season.iloc[i]
            sea=v[:i][g.season.values[:i]==s]
            rows.append(dict(pid=pid,name=g.player_display_name.iloc[i],pos=g.position.iloc[i],m=m,season=s,week=g.week.iloc[i],team=g.team.iloc[i],
              opp=g.opponent_team.iloc[i],gid=g.game_id.iloc[i],line=line,actual=v[i],y=float(v[i]>line),
              z=(h[:3].mean()-line)/sd,mu=((sea.mean() if len(sea)>=3 else avg)-line)/sd,pf=(h[:5]>line).mean()-.5,
              sd=sd/max(avg,1)))
r=pd.DataFrame(rows); print("rows",len(r),r.groupby("m").size().to_dict())
# opponent defense allowed per position: previous 5 games z
for m in MK:
    a=st[st.position.isin(MK[m][0].split())].groupby(["opponent_team","season","week"])[m].sum().reset_index().sort_values(["opponent_team","season","week"])
    a["prev5"]=a.groupby("opponent_team")[m].transform(lambda x:x.shift(1).rolling(5,min_periods=3).mean())
    lg=a.groupby(["season","week"])[m].transform("mean")
    a["od_"+m]=(a.prev5-a.groupby("season")[m].transform("mean"))/a[m].std()
    k=a.set_index(["opponent_team","season","week"])["od_"+m]
    idx=r.m==m; r.loc[idx,"od"]=[k.get((o,s,w),np.nan) for o,s,w in zip(r.opp[idx],r.season[idx],r.week[idx])]
r["od"]=r.od.fillna(0)
BASE=["z","mu","pf","od"]
# --- PFR player features (own previous 4 games)
def norm(n):
    t=re.sub(r"[^a-z ]","",str(n).lower()).split()
    while len(t)>2 and t[-1] in ("jr","sr","ii","iii","iv","v"): t=t[:-1]
    return "".join(t)
def pfr(kind,cols):
    d=pd.concat([pd.read_csv(f"{D}pfr_advstats_advstats_week_{kind}_{y}.csv") for y in YRS]); d=d[d.game_type=="REG"].copy()
    d["nm"]=d.pfr_player_name.map(norm); return d,cols
F={}
for kind,cols in (("pass",["passing_drop_pct","passing_bad_throw_pct","times_pressured_pct","times_blitzed","times_hurried"]),("rec",["receiving_broken_tackles","receiving_drop_pct","receiving_rat"]),("rush",["rushing_yards_before_contact_avg","rushing_yards_after_contact_avg","rushing_broken_tackles"])):
    d,cols=pfr(kind,cols); d=d.sort_values(["nm","season","week"])
    for c in cols:
        d["p4_"+c]=d.groupby("nm")[c].transform(lambda x:x.shift(1).rolling(4,min_periods=2).mean())
    F[kind]=(d.set_index(["nm","season","week"]),["p4_"+c for c in cols])
r["nm"]=r.name.map(norm)
KIND={"pyd":"pass","cmp":"pass","att":"pass","ryd":"rush","car":"rush","rec":"rec","recyd":"rec"}
feat=[]
for kind,(d,cols) in F.items():
    d=d[~d.index.duplicated()]
    for c in cols:
        r["pfr_"+c[3:]]=np.nan
        idx=r.m.map(KIND)==kind
        k=d[c]
        r.loc[idx,"pfr_"+c[3:]]=[k.get((n,s,w),np.nan) for n,s,w in zip(r.nm[idx],r.season[idx],r.week[idx])]
        feat.append("pfr_"+c[3:])
# --- FTN team features via pbp
frames=[]
for y in YRS:
    p=pd.read_csv(f"{D}pbp_{y}.csv.gz",usecols=["game_id","play_id","posteam","defteam","season_type"],low_memory=False)
    f=pd.read_csv(f"{D}ftn_charting_ftn_charting_{y}.csv",low_memory=False)
    f=f.merge(p,left_on=["nflverse_game_id","nflverse_play_id"],right_on=["game_id","play_id"],how="inner")
    frames.append(f)
f=pd.concat(frames); f=f[f.season_type=="REG"]
for c in ["is_play_action","is_no_huddle","is_motion","is_screen_pass","is_rpo","is_drop","is_qb_out_of_pocket","is_throw_away","is_contested_ball","is_created_reception","is_interception_worthy"]:
    f[c]=f[c].map(lambda v:1.0 if v in (True,1,"TRUE","True") else 0.0)
f["blitz"]=(f.n_blitzers.fillna(0)>0).astype(float); f["box"]=f.n_defense_box.astype(float)
f["rush8"]=(f.n_pass_rushers.fillna(0)>=5).astype(float)
cols=["is_play_action","is_no_huddle","is_motion","is_screen_pass","is_rpo","is_drop","is_qb_out_of_pocket","is_throw_away","is_contested_ball","is_created_reception","blitz","box","rush8","is_interception_worthy"]
off=f.groupby(["posteam","season","week"])[cols].mean().reset_index().rename(columns={"posteam":"team"}).sort_values(["team","season","week"])
dfn=f.groupby(["defteam","season","week"])[cols].mean().reset_index().rename(columns={"defteam":"team"}).sort_values(["team","season","week"])
def prev(df,k):
    o=df.copy()
    for c in cols: o[c]=o.groupby("team")[c].transform(lambda x:x.shift(1).rolling(k,min_periods=2).mean())
    return o.set_index(["team","season","week"])
O4,D5=prev(off,4),prev(dfn,5)
ftn=[]
for c in cols:
    ko,kd=O4[c],D5[c]
    r["ftnO_"+c]=[ko.get((t,s,w),np.nan) for t,s,w in zip(r.team,r.season,r.week)]
    r["ftnD_"+c]=[kd.get((t,s,w),np.nan) for t,s,w in zip(r.opp,r.season,r.week)]
    ftn+=["ftnO_"+c,"ftnD_"+c]
# --- referee crew
g=pd.read_csv(f"{D}games.csv"); 
of=pd.read_csv(f"{D}off.csv"); of=of[of.position=="Referee"]
g=g[(g.game_type=="REG")&g.season.isin(YRS)].copy(); g["tot"]=g.home_score+g.away_score
g=g.merge(of[["game_id","official_name"]].rename(columns={"game_id":"old_game_id"}),on="old_game_id",how="left").sort_values(["season","week"])
refrows=[]
hist={}
for _,x in g.iterrows():
    n=x.official_name; hs=hist.get(n,[])
    refrows.append((x.game_id, (np.mean(hs)-g.tot.mean()) if len(hs)>=15 else np.nan))
    if n==n and pd.notna(x.tot): hist.setdefault(n,[]).append(x.tot)
rf=dict(refrows); r["ref_tot"]=r.gid.map(rf)
ref=["ref_tot"]

# --- practice / injury report (nflverse injuries: one row per player-week)
inj = pd.concat([pd.read_csv(f"{D}inj_{y}.csv") for y in YRS])
inj = inj[inj.game_type == "REG"].drop_duplicates(["gsis_id", "season", "week"], keep="last").set_index(["gsis_id", "season", "week"])
k = list(zip(r.pid, r.season, r.week))
ps = pd.Series([inj.practice_status.get(x, np.nan) if x in inj.index else np.nan for x in k])
rs = pd.Series([inj.report_status.get(x, np.nan) if x in inj.index else np.nan for x in k])
r["inj_listed"] = (ps.notna() | rs.notna()).astype(float).values
r["inj_q"] = (rs == "Questionable").astype(float).values
r["inj_dnp"] = ps.fillna("").str.startswith("Did Not").astype(float).values
r["inj_limited"] = ps.fillna("").str.startswith("Limited").astype(float).values

BASE=["z","mu","pf","od"]
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
GROUPS={"pass":["pyd","cmp","att"],"rush":["ryd","car"],"rec":["rec","recyd"]}
feats=[c for c in r.columns if c.startswith(("pfr_","ftn","ref_","inj_"))]
def applies(f,m):
    if f.startswith("inj_") or f.startswith("ftn") or f.startswith("ref_"): return True
    if f.startswith("pfr_pass") or f.startswith("pfr_times"): return m in GROUPS["pass"]
    if f.startswith("pfr_rushing"): return m in GROUPS["rush"]
    if f.startswith("pfr_receiving"): return m in GROUPS["rec"]
    return True
out=[]
# overall base calibration check
for m in ["pyd","cmp","att","ryd","car","rec","recyd"]:
    s=r[r.m==m]; tr,te=s[s.season<=2024],s[s.season>=2025]
    b=logit(tr[BASE].values,tr.y.values); p=pred(te[BASE].values,b)
    print(f"base {m:6s} train n={len(tr)} test n={len(te)} test over-rate {te.y.mean():.3f}  base top20 hit {top(p,te.y.values)[0]:.3f}")
for m in ["pyd","cmp","att","ryd","car","rec","recyd"]:
    s=r[r.m==m]
    for f in feats:
        if not applies(f,m): continue
        d=s.dropna(subset=[f]); tr,te=d[d.season<=2024],d[d.season>=2025]
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
S.to_csv(""+D+"nfl_summary.csv",index=False)
print(f"\ntested {len(S)} feature/market combos")
print("positive dLL:",(S.dLL_e4>0).sum(),"| positive & same sign & |t|>=2:",((S.dLL_e4>0)&S.same_sign&(S.t.abs()>=2)).sum())
print("expected by chance at |t|>=2 (~5%):",round(len(S)*.05,1))
print(S.sort_values("t",ascending=False).head(14).to_string(index=False,float_format=lambda x:f"{x:.3f}"))
print("\nworst:"); print(S.sort_values("t").head(5).to_string(index=False,float_format=lambda x:f"{x:.3f}"))
