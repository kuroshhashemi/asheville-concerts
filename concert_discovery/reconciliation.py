"""Conservative display reconciliation; retain records and personal statuses."""
import re
from datetime import datetime
from difflib import SequenceMatcher

def same_bill(a,b):
 def tokens(x):
  x=re.sub(r'\s+(?:&|and)\s+friends\s*$','',x,flags=re.I)
  x=re.sub(r'\s*[-–:]?\s*\(?night\s+\d+\)?\s*$','',x,flags=re.I)
  words=re.findall(r'[a-z0-9]+',x.casefold())
  return words[1:] if len(words)>1 and words[0]=='the' else words
 x,y=tokens(a),tokens(b)
 if x==y:return True
 # Touring project suffixes are only accepted after a complete, multiword name.
 short,long=sorted((x,y),key=len)
 if len(short)>=2 and long[:len(short)]==short and (len(short)>=3 or long[len(short):len(short)+1]==['s']):return True
 return len(x)==len(y)>=2 and x[0]==y[0] and len(' '.join(x))>=12 and SequenceMatcher(None,' '.join(x),' '.join(y)).ratio()>=.92

def is_official(show):
 return any(x['source_name'].endswith('Official') for x in show.get('sources',[]))

def duplicate(a,b,all_shows):
 """One event identity rule for import, cleanup, and display.

 Room/date are mandatory. Shared support acts alone never prove a duplicate.
 Separate, explicitly timed official performances remain separate.
 """
 if a['venue_id']!=b['venue_id'] or a['performance_start'][:10]!=b['performance_start'][:10]:return False
 if ('patio' in a['title'].lower())!=('patio' in b['title'].lower()):return False
 ta,tb=a['performance_start'][11:16],b['performance_start'][11:16]
 oa,ob=is_official(a),is_official(b)
 if oa and ob and ta and tb and ta!=tb:return False
 ticket=lambda x:(x.get('ticket_url') or '').split('?')[0].rstrip('/')
 exact_ticket=bool(ticket(a) and ticket(a)==ticket(b))
 bill=same_bill(a['title'],b['title'])
 # Full headline sets must agree; one overlapping performer is insufficient.
 names=lambda x:{re.sub(r'[^a-z0-9]','',h['display_name'].casefold()) for h in x.get('headliners',[])}
 na,nb=names(a),names(b)
 bill=bill or bool(na and na==nb)
 if not (bill or exact_ticket):return False
 if not ta or not tb or ta==tb:return True
 if oa==ob:return False
 official,other=(a,b) if oa else (b,a)
 return compatible_time(official,other,[x for x in all_shows if is_official(x)])

def reconcile(shows):
 kept=[]
 # Deterministic official preference; stable oldest ID breaks equal-source ties.
 for show in sorted(shows,key=lambda s:(not is_official(s),s['show_id'])):
  if not any(duplicate(show,k,shows) for k in kept):kept.append(show)
 ids={s['show_id'] for s in kept}
 return [s for s in shows if s['show_id'] in ids]

def compatible_time(official,other,all_official):
 a,b=official['performance_start'][11:16],other['performance_start'][11:16]
 if not a or not b or a==b:return True
 same_night=[o for o in all_official if o['venue_id']==official['venue_id'] and o['performance_start'][:10]==official['performance_start'][:10] and same_bill(o['title'],official['title'])]
 if len(same_night)!=1:return False
 try:return abs((datetime.strptime(a,'%H:%M')-datetime.strptime(b,'%H:%M')).total_seconds())<=3600
 except ValueError:return False

def catalog_rows(c,venue_id=None,day=None):
 schema(c)
 where='WHERE show_id NOT IN (SELECT alias_id FROM show_aliases)'
 args=[]
 if venue_id:where+=' AND venue_id=?';args.append(venue_id)
 if day:where+=' AND substr(performance_start,1,10)=?';args.append(day)
 rows=[dict(r) for r in c.execute('SELECT * FROM shows '+where,args)]
 for r in rows:
  r['sources']=[dict(s) for s in c.execute('SELECT source_name FROM show_sources WHERE show_id=?',(r['show_id'],))]
  r['headliners']=[dict(a) for a in c.execute("SELECT display_name FROM artists JOIN show_artists USING(artist_id) WHERE show_id=? AND billing_role LIKE '%headliner%'",(r['show_id'],))]
 return rows

def schema(c):
 c.execute('CREATE TABLE IF NOT EXISTS show_aliases(alias_id INTEGER PRIMARY KEY,canonical_id INTEGER NOT NULL,reason TEXT,created_at TEXT)')

def canonical(c,sid):
 schema(c);seen=set()
 while sid not in seen:
  seen.add(sid);r=c.execute('SELECT canonical_id FROM show_aliases WHERE alias_id=?',(sid,)).fetchone()
  if not r:return sid
  sid=r[0]
 raise ValueError('Cyclic show aliases')

def key_aliases(db_path=None):
 from concert_discovery.storage import connect
 with connect(db_path) as c:
  schema(c)
  return {r['dedupe_key']:c.execute('SELECT dedupe_key FROM shows WHERE show_id=?',(canonical(c,r['show_id']),)).fetchone()[0] for r in c.execute('SELECT * FROM shows WHERE show_id IN (SELECT alias_id FROM show_aliases)').fetchall()}
