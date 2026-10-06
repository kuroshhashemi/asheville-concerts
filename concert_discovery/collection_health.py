"""Collection provenance and fail-closed completeness gates."""
import uuid
from concert_discovery.storage import connect,utc_now,DATABASE_PATH

def schema(c):
 c.execute('CREATE TABLE IF NOT EXISTS catalog_refresh_runs(run_id TEXT PRIMARY KEY,started_at TEXT,finished_at TEXT,state TEXT,detail TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS collection_health(run_id TEXT,venue_id TEXT,source_url TEXT,status TEXT,event_count INTEGER,pages INTEGER,observed_at TEXT,detail TEXT,PRIMARY KEY(run_id,venue_id,source_url))')

def start(db_path=DATABASE_PATH):
 rid=str(uuid.uuid4())
 with connect(db_path) as c:
  schema(c);c.execute('INSERT INTO catalog_refresh_runs VALUES(?,?,NULL,?,NULL)',(rid,utc_now(),'running'))
 return rid

def observation(rid,snapshot,db_path=DATABASE_PATH):
 count=len(set(snapshot['event_keys']))
 with connect(db_path) as c:
  schema(c)
  prior=c.execute("SELECT event_count FROM collection_health WHERE venue_id=? AND source_url=? AND status='complete' ORDER BY observed_at DESC LIMIT 1",(snapshot['venue_id'],snapshot['source_url'])).fetchone()
  suspicious=prior and prior[0]-count>=5 and count<prior[0]*.7
  status='drop_review' if suspicious else 'complete'
  detail='Large unexplained drop; absence retirement disabled' if suspicious else 'All calendar pages and event cards parsed'
  c.execute('INSERT OR REPLACE INTO collection_health VALUES(?,?,?,?,?,?,?,?)',(rid,snapshot['venue_id'],snapshot['source_url'],status,count,snapshot.get('pages',1),utc_now(),detail))
 return not suspicious

def finish(rid,warnings,db_path=DATABASE_PATH):
 with connect(db_path) as c:
  schema(c);c.execute('UPDATE catalog_refresh_runs SET finished_at=?,state=?,detail=? WHERE run_id=?',(utc_now(),'warning' if warnings else 'complete','; '.join(warnings),rid))

def summary(db_path=DATABASE_PATH):
 with connect(db_path) as c:
  schema(c)
  rows=[dict(r) for r in c.execute("SELECT h.*,v.name venue FROM collection_health h LEFT JOIN venues v USING(venue_id) WHERE h.status!='test' ORDER BY observed_at DESC")]
  latest={}
  for r in rows:
   if r['venue_id'] not in latest:
    r['last_complete']=next((x['observed_at'] for x in rows if x['venue_id']==r['venue_id'] and x['status']=='complete'),None);latest[r['venue_id']]=r
  run=c.execute("SELECT * FROM catalog_refresh_runs WHERE state!='test' ORDER BY started_at DESC LIMIT 1").fetchone()
  jobs=[]
  if c.execute("SELECT 1 FROM sqlite_master WHERE name='artist_matching_jobs'").fetchone():jobs=[dict(r) for r in c.execute("SELECT state,count(*) count FROM artist_matching_jobs GROUP BY state")]
 from concert_discovery.discovery import get_shows
 visible={a['artist_id'] for show in get_shows(db_path) for a in show['headliners'] if a.get('entity_kind')=='artist'}
 with connect(db_path) as c:
  counts={}
  if c.execute("SELECT 1 FROM sqlite_master WHERE name='artist_matching_jobs'").fetchone():
   for r in c.execute('SELECT artist_id,state FROM artist_matching_jobs'):
    if r['artist_id'] in visible:counts[r['state']]=counts.get(r['state'],0)+1
 jobs=[dict(state=k,count=v) for k,v in sorted(counts.items())]
 return list(latest.values()),dict(run) if run else None,jobs


CORE={'brevard-music-center':'https://www.brevardmusic.org/events/','asheville-music-hall':'https://ashevillemusichall.com/all-shows/','one-stop':'https://ashevillemusichall.com/all-shows/','eulogy':'https://burialbeer.com/pages/eulogy','orange-peel':'https://theorangepeel.net/events/','hellbender':'https://theorangepeel.net/events/','grey-eagle':'https://www.thegreyeagle.com/calendar/','harrahs-arena':'https://www.harrahscherokeecenterasheville.com/events-tickets/','thomas-wolfe':'https://www.harrahscherokeecenterasheville.com/events-tickets/','sierra-nevada':'https://sierranevada.com/events'}

def missing_checks(rid,checked,warnings,db_path=DATABASE_PATH,expected_venues=None):
 with connect(db_path) as c:
  schema(c)
  for vid,url in CORE.items():
   if expected_venues is not None and vid in expected_venues and vid not in checked:
    detail='No complete calendar snapshot; cached listings retained'
    c.execute('INSERT OR REPLACE INTO collection_health VALUES(?,?,?,?,?,?,?,?)',(rid,vid,url,'incomplete',None,None,utc_now(),detail))
    warnings.append(vid+': '+detail)


def warning(db_path=DATABASE_PATH):
 from datetime import datetime,timezone,timedelta
 checks,run,_=summary(db_path)
 cutoff=datetime.now(timezone.utc)-timedelta(hours=48)
 by_id={r['venue_id']:r for r in checks};names=[]
 with connect(db_path) as c:
  venues={r['venue_id']:r['name'] for r in c.execute('SELECT * FROM venues')}
 for vid in CORE:
  row=by_id.get(vid);stamp=row.get('observed_at') if row else None
  fresh=False
  if stamp:
   try:fresh=datetime.fromisoformat(stamp.replace('Z','+00:00')).replace(tzinfo=timezone.utc)>=cutoff
   except ValueError:pass
  if not row or row['status']!='complete' or not fresh:names.append(venues.get(vid,vid))
 names=list(dict.fromkeys(names))
 return (', '.join(names)+' data awaiting sync') if names else None
