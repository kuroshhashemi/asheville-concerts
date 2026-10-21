"""Durable field outcomes derived from saved collection evidence; no network calls."""
from datetime import datetime,timedelta,timezone
from collections import Counter
from concert_discovery.storage import connect,DATABASE_PATH,utc_now

FIELDS=('spotify','listeners','photo','genre','growth')

def schema(c):
 c.execute('''CREATE TABLE IF NOT EXISTS metadata_outcomes(
 entity_type TEXT,entity_key TEXT,field TEXT,status TEXT,checked_at TEXT,next_attempt_at TEXT,detail TEXT,
 first_seen_at TEXT,first_failure_at TEXT,consecutive_failures INTEGER DEFAULT 0,active INTEGER DEFAULT 1,
 PRIMARY KEY(entity_type,entity_key,field))''')
 if 'active' not in {r[1] for r in c.execute('PRAGMA table_info(metadata_outcomes)')}:c.execute('ALTER TABLE metadata_outcomes ADD COLUMN active INTEGER DEFAULT 1')

def record(c,entity_type,key,field,status,checked=None,retry=None,detail='',now=None):
 now=now or utc_now();schema(c)
 old=c.execute('SELECT * FROM metadata_outcomes WHERE entity_type=? AND entity_key=? AND field=?',(entity_type,key,field)).fetchone()
 first=old['first_seen_at'] if old else now
 failure=(old['first_failure_at'] or now) if old and status=='blocked' and old['status']=='blocked' else now if status=='blocked' else None
 n=0
 if status=='blocked':n=(old['consecutive_failures'] if old and old['status']=='blocked' else 0)+(0 if old and old['status']=='blocked' and old['checked_at']==checked else 1)
 c.execute('INSERT OR REPLACE INTO metadata_outcomes VALUES(?,?,?,?,?,?,?,?,?,?,?)',(entity_type,str(key),field,status,checked,retry,str(detail or '')[:500],first,failure,n,1))

def synchronize(db_path=DATABASE_PATH):
 from concert_discovery.discovery import get_shows
 from concert_discovery.prices import load,for_show,url_key
 from concert_discovery.pricing_health import report
 shows=get_shows(db_path);prices=load();_,ticket_gaps=report(shows,prices,db_path);gaps={r['Tickets']:r for r in ticket_gaps}
 artists={a['artist_id']:a for s in shows for a in s['headliners']}
 now=utc_now();stats=Counter()
 with connect(db_path) as c:
  schema(c);c.execute('UPDATE metadata_outcomes SET active=0');tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  def rows(table):return [dict(r) for r in c.execute('SELECT * FROM '+table)] if table in tables else []
  icon_checks={r['venue_id']:r for r in rows('venue_icon_checks')}
  artwork={r['artist_id']:r for r in rows('artwork_checks')}
  ticket_checks={}
  for table in ('ticket_price_checks','brightdata_price_checks','rendered_price_checks','cloud_rendered_price_checks','ticketmaster_price_checks'):
   for r in rows(table):ticket_checks.setdefault(r.get('url_key') or r.get('event_id'),[]).append(r)
  provider_checks={r['provider']:r for r in rows('growth_provider_checks')}
  growth_queue={r['spotify_id']:r for r in rows('growth_queue')}
  jobs={r['artist_id']:r for r in rows('artist_matching_jobs')};images={r['artist_id']:r for r in rows('artist_images')};hist={r['spotify_id']:r for r in rows('history_checks')};metrics={}
  for r in sorted(rows('artist_metric_snapshots'),key=lambda r:r['retrieved_at'],reverse=True):metrics.setdefault((r['artist_id'],r['source_url']),r)
  def put(kind,key,field,state,checked=None,retry=None,detail=''):
   record(c,kind,key,field,state,checked,retry,detail,now);stats[state]+=1
  for aid,a in artists.items():
   sid=a.get('spotify_artist_id');job=jobs.get(aid,{})
   state='complete' if sid else 'not_applicable' if a.get('entity_kind','artist')!='artist' else 'blocked' if job.get('state')=='blocked' else 'unresolved' if job.get('state')=='ambiguous' else 'pending'
   put('artist',aid,'spotify',state,job.get('last_attempt_at'),job.get('next_attempt_at'),job.get('detail','Existing identity retained' if sid else 'Waiting for matching'))
   if not sid:
    for f in ('listeners','photo','growth'):put('artist',aid,f,'not_applicable' if state=='not_applicable' else 'waiting_for_identity',detail='Requires a verified Spotify identity')
   else:
    m=metrics.get((aid,a.get('spotify_profile_url')),{})
    ms='blocked' if m and m.get('status') not in ('success','metrics_unavailable') else 'complete' if a.get('monthly_listeners') is not None else 'unavailable' if m.get('status')=='metrics_unavailable' else 'pending'
    put('artist',aid,'listeners',ms,m.get('retrieved_at'),detail=m.get('detail','No saved observation'))
    im=images.get(aid,{})
    art=artwork.get(aid,{})
    photo_state='complete' if a.get('image_url') else 'unavailable' if art.get('status')=='unresolved' else art.get('status','pending')
    put('artist',aid,'photo',photo_state,art.get('checked_at') or im.get('updated_at'),detail=art.get('detail','Saved Spotify artwork' if a.get('image_url') else 'No successful artwork observation yet'))
    h=hist.get(sid,{})
    hs='blocked' if h.get('status') in ('blocked','rate_limited','request_error','parse_error') else 'complete' if a.get('growth_detail') else 'unavailable' if h.get('status') in ('not_found','no_history','history') else 'queued'
    provider=provider_checks.get('pastspot',{})
    queue_detail=growth_queue.get(sid,{}).get('reason','Queued for growth check')
    if not h and provider.get('status') in ('blocked','rate_limited'):queue_detail='Queued: growth provider access unavailable; no artist request attempted'
    retry=None
    if h.get('checked_at'):
     days=90 if h.get('status') in ('history','not_found','no_history') else 1
     retry=(datetime.fromisoformat(h['checked_at'].replace('Z','+00:00'))+timedelta(days=days)).isoformat()
    put('artist',aid,'growth',hs,h.get('checked_at'),retry,'Six-month comparison available' if hs=='complete' else 'No usable six-month comparison in saved history' if hs=='unavailable' else h.get('status',queue_detail))
   put('artist',aid,'genre','complete' if a.get('genre') else 'unavailable',detail='Structured JamBase genre' if a.get('genre') else 'Chosen genre source supplied no genre; other sources intentionally unused')
  for s in shows:
   key=s['dedupe_key'];p=for_show(s,prices);url=s.get('ticket_url') or s.get('official_event_url');g=gaps.get(url,{})
   from concert_discovery.ticketmaster_prices import event_id
   urls=[url]+[r['source_url'] for r in s.get('sources',[])];ids={url_key(u) for u in urls if u}|{event_id(u) for u in urls if event_id(u)}
   checks=[r for k in ids for r in ticket_checks.get(k,[])];latest=max(checks,key=lambda r:r.get('checked_at',''),default={})
   failed=latest.get('status') in ('blocked','error','failed','blocked_or_unavailable') and (not p or latest.get('checked_at','')>p.get('observed_at',p.get('checked_at','')))
   state='complete' if s.get('sold_out') else 'unavailable' if s.get('on_sale_label') else 'blocked' if failed else 'complete' if p is not None else 'blocked' if g.get('Reason') in ('Access blocked','Collection failed') else 'pending' if g.get('Reason') in ('Not checked','Saved price missing') else 'unavailable' if g.get('Reason')=='Tickets unavailable' or latest.get('status')=='unavailable' else 'unresolved'
   checked=latest.get('checked_at') or (p.get('observed_at') if p else None)
   retry=s.get('on_sale_at')
   if checked and state=='blocked':retry=(datetime.fromisoformat(checked.replace('Z','+00:00'))+timedelta(days=1)).isoformat()
   put('show',key,'tickets',state,checked,retry,latest.get('status') if failed else g.get('Reason','Sold Out' if s.get('sold_out') else 'Saved price or resale'))
   for f,good in (('date',s.get('performance_start')),('venue',s.get('venue_name')),('title',s.get('title')),('type',s.get('event_classification'))):
    put('show',key,f,'complete' if good else 'pending',detail='Saved source data or classification')
  for vid in {s['venue_id'] for s in shows}:
   good=next((s.get('venue_icon') for s in shows if s['venue_id']==vid),None);ic=icon_checks.get(vid,{})
   put('venue',vid,'venue_icon','complete' if good else ic.get('status','queued'),ic.get('checked_at'),detail=ic.get('detail','Saved venue icon' if good else 'Queued for favicon discovery'))
 return {'metadata_outcomes':dict(stats)}


def admin_view(st,identity,owner_email,db_path=DATABASE_PATH):
 from concert_discovery.activity import is_owner
 if not is_owner(identity,owner_email):return
 with st.expander('Metadata health · owner only'):
  with connect(db_path) as c:
   if not c.execute("SELECT 1 FROM sqlite_master WHERE name='metadata_outcomes'").fetchone():
    st.caption('Field outcomes will appear after the next collection.');return
   rows=[dict(r) for r in c.execute("""SELECT m.*,COALESCE(a.display_name,s.title,m.entity_key) display_name
    FROM metadata_outcomes m LEFT JOIN artists a ON m.entity_type='artist' AND a.artist_id=m.entity_key
    LEFT JOIN shows s ON m.entity_type='show' AND s.dedupe_key=m.entity_key WHERE m.active=1 ORDER BY m.status,m.field,display_name""")]
  st.caption('Saved field outcomes; opening this view makes no collection requests. Unavailable data and unmatched identities are separate from failed fetches.')
  counts=Counter(r['status'] for r in rows);st.write(' · '.join(f'{k}: {v}' for k,v in sorted(counts.items())))
  all_states=st.checkbox('Include completed and unavailable fields',value=False,key='metadata_health_all')
  visible=rows if all_states else [r for r in rows if r['status'] in ('blocked','pending','queued','unresolved')]
  st.dataframe([{'Artist / show':r['display_name'],'Field':r['field'],'State':r['status'],'Last check':r['checked_at'],'Retry eligible':r['next_attempt_at'],'Detail':r['detail']} for r in visible],hide_index=True,width='stretch')
