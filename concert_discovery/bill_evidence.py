"""Cached official bill evidence; event titles are never treated as identities blindly."""
import json,re
from datetime import datetime,timezone,timedelta
import requests
from concert_discovery.storage import connect,utc_now,DATABASE_PATH
from concert_discovery.official_calendar import Tree
from concert_discovery.event_classification import classify

def schema(c):
 c.execute('CREATE TABLE IF NOT EXISTS event_page_cache(source_url TEXT PRIMARY KEY,markup TEXT,checked_at TEXT,state TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS bill_evidence_versions(source_key TEXT PRIMARY KEY,version INTEGER)')
 c.execute('CREATE TABLE IF NOT EXISTS bill_evidence(source_key TEXT PRIMARY KEY,source_url TEXT,category TEXT,entity_kind TEXT,performers TEXT,evidence TEXT,checked_at TEXT,state TEXT)')

def inspect(markup):
 tree=Tree();tree.feed(markup)
 def body_nodes(node):
  if node.tag in ('footer','nav','header','aside','script'):return
  yield node
  for child in node.children:
   if hasattr(child,'tag'):yield from body_nodes(child)
 text=' '.join(n.text() for n in body_nodes(tree.root) if n.tag=='p')
 title=next((n.text() for n in tree.root.walk() if n.tag=='h1'),'')
 category,reason=classify(title+' '+text)
 # Exclusion decisions use event-card/structured labels, not unrelated page prose.
 # Keep explicit non-music category evidence for later catalog classification.
 series=bool(re.search(r'each event showcases|lineup is revealed only when|recurring (?:concert|music|show) series',text,re.I))
 performers=[]
 def visit(obj):
  nonlocal category,reason
  if isinstance(obj,list):
   for v in obj:visit(v)
  elif isinstance(obj,dict):
   if obj.get('@type') in ('Event','MusicEvent','ComedyEvent','DanceEvent','TheaterEvent','SportsEvent'):
    typed={'ComedyEvent':'comedy','DanceEvent':'dance','TheaterEvent':'theatre','SportsEvent':'sports'}
    explicit=typed.get(obj.get('@type'))
    detected,detail=classify(str(obj.get('name',''))+' '+str(obj.get('description',''))+' '+str(obj.get('genre','')))
    if explicit:category,reason=explicit,'Structured event type: '+obj['@type']
    elif detected!='unknown' and category=='unknown':category,reason=detected,detail
    values=obj.get('performer',[])
    if isinstance(values,dict):values=[values]
    for v in values:
     if isinstance(v,dict) and v.get('name'):performers.append(dict(name=v['name'],role='headliner',confidence=1,note='Structured official event performer'))
   for k in ('@graph','event','itemListElement','item'):
    if k in obj:visit(obj[k])
 for n in tree.root.walk():
  if n.tag=='script' and n.attrs.get('type')=='application/ld+json':
   try:visit(json.loads(n.text()))
   except (ValueError,TypeError):pass
 # Explicit linked artist headings, corroborated by the event title, are another
 # source-provided lineup format. Footer/social links never establish performers.
 if not performers:
  from urllib.parse import urlparse
  title=next((n.text() for n in tree.root.walk() if n.tag=='h1'),'')
  for n in tree.root.walk():
   if n.tag!='a' or not any(x.tag=='strong' for x in n.walk()):continue
   host=urlparse(n.attrs.get('href','')).hostname or ''
   label=n.text().strip()
   if not host or any(x in host for x in ('instagram','facebook','twitter','youtube','etix','ticket','google')):continue
   if len(label)>=3 and re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',title,re.I):
    performers.append(dict(name=label.title() if label.isupper() else label,role='headliner',confidence=1,note='Explicit linked performer heading corroborated by bill title'))
 if series:category,reason='events','Explicit recurring showcase description'
 return dict(category=category,entity_kind='series' if series else None,performers=performers,evidence=reason if category!='unknown' else 'Explicit recurring showcase description' if series else 'Structured source performer data' if performers else 'No explicit additional evidence')

def save(c,event,evidence):
 schema(c)
 c.execute('INSERT OR REPLACE INTO bill_evidence VALUES(?,?,?,?,?,?,?,?)',(event['source_key'],event['source_url'],evidence.get('category','unknown'),evidence.get('entity_kind'),json.dumps(evidence.get('performers',[])),evidence['evidence'],utc_now(),'success'))
 c.execute('INSERT OR REPLACE INTO bill_evidence_versions VALUES(?,3)',(event['source_key'],))
 if evidence.get('category','unknown')!='unknown':
  from concert_discovery.event_classification import save as save_category
  for row in c.execute('SELECT show_id FROM show_sources WHERE source_key=?',(event['source_key'],)).fetchall():
   save_category(c,row['show_id'],dict(event,category_override=evidence['category'],category_evidence=evidence['evidence']))

def enrich_events(events,db_path=DATABASE_PATH,budget=None):
 """First-pass description checks before import, four requests at a time.

 Normal refreshes have no eight-page count limit. Explicit budgets are retained
 only for caller-requested probes. Successful pages are reused for thirty days;
 failed requests retry after a day. Shared event URLs are fetched once.
 """
 from concurrent.futures import ThreadPoolExecutor,as_completed
 from urllib.parse import urlparse
 with connect(db_path) as c:
  schema(c)
  cache={r['source_key']:dict(r) for r in c.execute('SELECT * FROM bill_evidence')}
  versions={r[0]:r[1] for r in c.execute('SELECT * FROM bill_evidence_versions')}
  pages={r['source_url']:dict(r) for r in c.execute('SELECT * FROM event_page_cache')}
 cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
 retry_after=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
 grouped={}
 for e in events:
  url=e.get('source_url','');parsed=urlparse(url)
  if parsed.scheme not in ('http','https') or parsed.hostname in ('open.spotify.com','api.spotify.com'):continue
  prior=cache.get(e['source_key'])
  if prior and prior['checked_at']>=(retry_after if prior['state']=='failed' else cutoff) and (prior['state']=='failed' or versions.get(e['source_key'])==3):continue
  page=pages.get(url)
  if page and page['checked_at']>=(retry_after if page['state']=='failed' else cutoff):
   if page['state']=='success':
    with connect(db_path) as c:save(c,e,inspect(page['markup']))
   continue
  grouped.setdefault(url,[]).append(e)
 urls=list(grouped)
 if budget is not None:urls=urls[:budget]
 def fetch(url):
  try:
   response=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=15);response.raise_for_status()
   return url,response.text,None
  except requests.RequestException as error:return url,None,type(error).__name__
 with ThreadPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(fetch,url) for url in urls]
  for future in as_completed(futures):
   url,markup,error=future.result()
   with connect(db_path) as c:
    c.execute('INSERT OR REPLACE INTO event_page_cache VALUES(?,?,?,?)',(url,markup,utc_now(),'failed' if error else 'success'))
    for event in grouped[url]:
     if not error:save(c,event,inspect(markup))
     else:c.execute('INSERT INTO bill_evidence VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET checked_at=excluded.checked_at,state=excluded.state',(event['source_key'],url,'unknown',None,'[]','Description unavailable; category remains unverified',utc_now(),'failed'))
 return len(urls)

def apply(c,event):
 schema(c);row=c.execute('SELECT * FROM bill_evidence WHERE source_key=?',(event['source_key'],)).fetchone()
 if not row:return event
 event=dict(event)
 if row['category']!='unknown':event['category_override']=row['category'];event['category_evidence']=row['evidence']
 performers=json.loads(row['performers'])
 if performers:event['performers']=performers
 if row['entity_kind']:
  from concert_discovery.spotify_matching import name_key
  c.execute('CREATE TABLE IF NOT EXISTS artist_entity_types(name_key TEXT PRIMARY KEY,kind TEXT,evidence TEXT)')
  c.execute('INSERT OR REPLACE INTO artist_entity_types VALUES(?,?,?)',(name_key(event['title']),row['entity_kind'],row['evidence']+'; '+row['source_url']))
 return event


def research_catalog(db_path=DATABASE_PATH,budget=None):
 """Research current official listings without recollecting calendars or calling APIs."""
 from concert_discovery.discovery import get_shows
 events=[]
 for show in get_shows(db_path):
  if not show['event_classification'].get('assumed'):continue
  for source in show['sources']:
   if source['source_name'].endswith('Official'):
    events.append(dict(source,title=show['title']))
 return enrich_events(events,db_path,budget)
