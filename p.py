import json,urllib.request,datetime as dt
H={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
def g(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30).read())
out={}
today=dt.date.today()
# 1. finished EPL match roster stats (all stat names, starter, subbed flags)
evs=[]
for k in range(1,15):
    evs+=[e for e in g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={today-dt.timedelta(days=k):%Y%m%d}").get('events',[]) if e['status']['type']['state']=='post']
    if evs: break
s=g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event={evs[0]['id']}")
r=s['rosters'][0]
p=[x for x in r['roster'] if x.get('starter') and x['position']['abbreviation']!='G'][0]
out['stat_names']=[ (st['name'],st.get('value')) for st in p['stats']]
out['player_keys']=list(p.keys())
out['team']=r['team'].get('abbreviation'),r['team'].get('id'),r['team'].get('displayName')
sub=[x for x in r['roster'] if x.get('subbedIn')]
out['sub_example']={k:sub[0].get(k) for k in ('subbedIn','subbedOut','starter','active')} if sub else None
out['sub_stats']=[(st['name'],st.get('value')) for st in sub[0]['stats']][:30] if sub else None
out['keyEvents_sample']=[ (ke.get('type',{}).get('text'),ke.get('clock',{}).get('displayValue'),[a.get('athlete',{}).get('id') for a in ke.get('participants',[])]) for ke in s.get('keyEvents',[])[:12]]
# 2. upcoming match: scoreboard odds fields, propBets pagination, team roster endpoint
up=[]
for k in range(0,4):
    up+=[e for e in g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={today+dt.timedelta(days=k):%Y%m%d}").get('events',[]) if e['status']['type']['state']=='pre']
    if up: break
e=up[0];c=e['competitions'][0]
out['sb_odds']=c.get('odds')
out['competitors']=[(x['team']['abbreviation'],x['team']['id'],x['homeAway']) for x in c['competitors']]
pb=g(f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1/events/{e['id']}/competitions/{e['id']}/odds/100/propBets?limit=1000")
out['pb_count']=pb.get('count'),pb.get('pageCount'),len(pb.get('items',[]))
ag=[it for it in pb['items'] if it['type']['name']=='Anytime Goalscorer'][:2]
out['ag_items']=ag
tid=c['competitors'][0]['team']['id']
ro=g(f"https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/teams/{tid}/roster")
out['roster_keys']=list(ro.keys())
a=(ro.get('athletes') or [{}])[0]
out['roster_athlete']={k:a.get(k) for k in ('id','displayName','position','jersey')} if a else None
out['roster_n']=len(ro.get('athletes') or [])
# 3. league list
try:
    lg=g("https://site.api.espn.com/apis/site/v2/sports/soccer/leagues?limit=400")
    out['leagues']=[ (l.get('slug'),l.get('name')) for l in lg.get('leagues',[])][:400]
except Exception as x: out['leagues']=str(x)
json.dump(out,open('out/soc2.json','w'),indent=1,default=str)
print(json.dumps(out,default=str)[:20000])
