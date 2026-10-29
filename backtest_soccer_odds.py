"""Soccer team-bet backtest (Oct 28): football-data.co.uk results and odds (16 leagues, 2021-22 to now, about 24,600
matches). Pinnacle's pre-closing prices give the fair chances; Bet365 / the market average / the best quoted price play
the soft book the app bets at. Reports Pinnacle's calibration, the ROI of betting whenever a soft price beats the fair price
by X, ROI by claimed-edge bucket and odds bucket, and then compares three ways of removing the margin (proportional,
power, Shin). Result (Oct 28): Pinnacle is accurate for 20-70% outcomes but outcomes under 20% win about 11% less often than
the proportional method says (Shin cuts that gap about in half); claimed edges of 5%+ at the best price lost 3-17%; bets
above +700 lost 27%; Bet365 beating Pinnacle by 2%+ made about +4% on 1,772 bets (standard error about 5%).
soccer_team.py uses Shin and drops main-market bets above a 6% claimed edge because of this.
Usage: python backtest_soccer_odds.py [data_dir]  (downloads about 100 league-season files, a few MB)
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
import pandas as pd, numpy as np, glob, warnings
warnings.filterwarnings("ignore")
LEAGUES = "E0 E1 SC0 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1".split()
SEASONS = ["2122", "2223", "2324", "2425", "2526", "2627"]
for s in SEASONS:
    for lg in LEAGUES:
        fetch(f"https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv", f"{s}_{lg}.csv")
fs = sorted(glob.glob(D + "2*_*.csv")); L = []
for f in fs:
    d=pd.read_csv(f,encoding="latin1"); d.columns=[c.replace("﻿","").replace("ï»¿","") for c in d.columns]
    d["season"]=f.split("/")[-1][:4]; d["lg"]=d.get("Div"); L.append(d)
d=pd.concat(L,ignore_index=True); d=d.dropna(subset=["FTHG","FTAG","PSH","PSD","PSA"]); print("matches",len(d), d.groupby("season").size().to_dict())
rows=[]
def add(d_,market,sel,soft,fairp_open,fairp_close,won,tag):
    rows.append(pd.DataFrame(dict(season=d_.season,lg=d_.lg,market=market,sel=sel,soft=soft,fo=fairp_open,fc=fairp_close,won=won,book=tag)))
# de-vig proportional
def dv(*odds):
    inv=[1/o for o in odds]; s=sum(inv); return [i/s for i in inv]
ph,pd_,pa=dv(d.PSH,d.PSD,d.PSA)
has_c=d.PSCH.notna()
cph,cpd,cpa=dv(d.PSCH.fillna(d.PSH),d.PSCD.fillna(d.PSD),d.PSCA.fillna(d.PSA))
res={"H":d.FTHG>d.FTAG,"D":d.FTHG==d.FTAG,"A":d.FTHG<d.FTAG}
for sel,(o,c,w) in {"H":(ph,cph,res["H"]),"D":(pd_,cpd,res["D"]),"A":(pa,cpa,res["A"])}.items():
    for tag,col in (("B365",f"B365{sel}"),("Max",f"Max{sel}"),("Avg",f"Avg{sel}")):
        if col in d: add(d,"1X2",sel,d[col],o,c,w.astype(float),tag)
tot=d.FTHG+d.FTAG
if "P>2.5" in d:
    o_ov,o_un=dv(d["P>2.5"],d["P<2.5"]); c_ov,c_un=dv(d["PC>2.5"].fillna(d["P>2.5"]),d["PC<2.5"].fillna(d["P<2.5"]))
    for sel,(o,c,w) in {"Over2.5":(o_ov,c_ov,tot>2.5),"Under2.5":(o_un,c_un,tot<2.5)}.items():
        for tag,col in (("B365","B365"+(">2.5" if sel[0]=="O" else "<2.5")),("Max","Max"+(">2.5" if sel[0]=="O" else "<2.5")),("Avg","Avg"+(">2.5" if sel[0]=="O" else "<2.5"))):
            if col in d: add(d,"OU2.5",sel,d[col],o,c,w.astype(float),tag)
r=pd.concat(rows,ignore_index=True).dropna(subset=["soft","fo","fc","won"])
r=r[r.soft>1.01]; r["edge"]=r.soft*r.fo-1; r["pnl"]=np.where(r.won==1,r.soft-1,-1.0); r["clv"]=r.soft*r.fc-1
print("\nPinnacle calibration (pre-closing fair prob vs outcome):")
c=r[r.book=="B365"].copy(); c["b"]=pd.cut(c.fo,[0,.1,.2,.3,.4,.5,.6,.7,.8,1])
print(c.groupby("b").agg(n=("won","size"),pred=("fo","mean"),actual=("won","mean")).round(3).to_string())
print("\nBet whenever soft price beats Pinnacle fair by >= X (price shown pre-kickoff, ROI at soft price):")
for tag in ("B365","Avg","Max"):
    t=r[r.book==tag]
    for th in (0,.02,.05,.10):
        s=t[t.edge>=th]
        if len(s)<30: continue
        print(f"{tag:5s} edge>={th:.2f} n={len(s):6d} avgEdge {s.edge.mean():+.3f} ROI {s.pnl.mean():+.3f} (se {s.pnl.std()/np.sqrt(len(s)):.3f})  hit {s.won.mean():.3f} vs fair {s.fo.mean():.3f}  CLV(vs Pin close) {s.clv.mean():+.3f}")
print("\nMax-odds bets with edge>=2% by season / by odds bucket / by market:")
m=r[(r.book=="Max")&(r.edge>=.02)]
for k in ("season","market","sel"):
    print(m.groupby(k).agg(n=("pnl","size"),edge=("edge","mean"),roi=("pnl","mean"),hit=("won","mean"),fair=("fo","mean")).round(3).to_string()); print()
m["ob"]=pd.cut(m.soft,[1,1.8,2.5,4,8,100]); print(m.groupby("ob").agg(n=("pnl","size"),edge=("edge","mean"),roi=("pnl","mean"),hit=("won","mean"),fair=("fo","mean")).round(3).to_string())
print("\nrealized ROI vs claimed edge (Max, all bets) by edge bucket:")
t=r[r.book=="Max"].copy(); t["eb"]=pd.cut(t.edge,[-1,-.1,-.05,-.02,0,.02,.05,.1,1])
print(t.groupby("eb").agg(n=("pnl","size"),claimed=("edge","mean"),roi=("pnl","mean")).round(3).to_string())


print("\n===== de-vig methods vs the favourite-longshot bias (1X2, Bet365 and best-price quotes) =====")
L = []
for f in sorted(glob.glob(D + "2*_*.csv")):
    x = pd.read_csv(f, encoding="latin1"); x.columns = [c.replace("\ufeff", "").replace("\u00ef\u00bb\u00bf", "").replace("ï»¿", "") for c in x.columns]; x["season"] = f.split("/")[-1][:4]; L.append(x)
d = pd.concat(L, ignore_index=True).dropna(subset=["FTHG", "FTAG", "PSH", "PSD", "PSA", "B365H", "B365D", "B365A"]).reset_index(drop=True)
O=d[["PSH","PSD","PSA"]].values; inv=1/O
def power(inv):
    out=np.zeros_like(inv)
    for i,x in enumerate(inv):
        lo,hi=1.0,3.0
        for _ in range(40):
            k=(lo+hi)/2
            if (x**k).sum()>1: lo=k
            else: hi=k
        out[i]=x**k
    return out
def shin(inv):
    out=np.zeros_like(inv); n=inv.shape[1]
    for i,x in enumerate(inv):
        B=x.sum(); lo,hi=0,.4
        for _ in range(40):
            z=(lo+hi)/2; p=(np.sqrt(z*z+4*(1-z)*x*x/B)-z)/(2*(1-z))
            if p.sum()>1: lo=z
            else: hi=z
        out[i]=p/p.sum()
    return out
prop=inv/inv.sum(1,keepdims=True); pw=power(inv); sh=shin(inv)
res=np.column_stack([d.FTHG>d.FTAG,d.FTHG==d.FTAG,d.FTHG<d.FTAG]).astype(float)
print("longshot calibration (prob<0.20, all 3 outcomes pooled):")
for nm,p in (("proportional",prop),("power",pw),("shin",sh)):
    m=p<.2; print(f"  {nm:13s} n={m.sum()} pred {p[m].mean():.4f} actual {res[m].mean():.4f}")
    m=(p>=.2)&(p<.4); print(f"  {'':13s} 0.2-0.4: pred {p[m].mean():.4f} actual {res[m].mean():.4f}")
    m=p>=.4; print(f"  {'':13s} >=0.4 : pred {p[m].mean():.4f} actual {res[m].mean():.4f}")
soft=d[["B365H","B365D","B365A"]].values
for tag,sf in (("B365",soft),("Max",d[["MaxH","MaxD","MaxA"]].values)):
    ok=~np.isnan(sf).any(1)
    for nm,p in (("proportional",prop),("power",pw),("shin",sh)):
        e=(sf*p-1)[ok]; pnl=np.where(res[ok]==1,sf[ok]-1,-1.0)
        print(f"\n{tag} soft price, fair by {nm}: ROI by claimed-edge bucket")
        bk=pd.cut(pd.Series(e.ravel()),[-1,-.05,-.02,0,.02,.05,.10,1])
        t=pd.DataFrame(dict(b=bk,e=e.ravel(),p=pnl.ravel()))
        g=t.groupby("b").agg(n=("p","size"),claimed=("e","mean"),roi=("p","mean")).round(3); print(g.tail(4).to_string())
