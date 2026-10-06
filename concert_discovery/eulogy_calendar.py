"""Follow the same public feed and next links used by Eulogy's DICE widget."""
import json,re,uuid
from datetime import datetime,date
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import requests
from concert_discovery.api_sources import event
from concert_discovery.event_sources import parse_performers,venue_id_for
PAGE='https://burialbeer.com/pages/eulogy'
ENDPOINT='https://partners-endpoint.dice.fm/api/v2/events'

def parse_event(e,today=None):
 today=today or date.today()
 if not any(venue_id_for(v.get('name',''))=='eulogy' for v in e.get('venues',[])):return None
 if e.get('is_multi_days_event'):return None # Ticket bundle, not an extra performance.
 cancelled=bool(e.get('cancelled') or e.get('canceled') or e.get('status') in ('cancelled','canceled'))
 start=datetime.fromisoformat(e['date'].replace('Z','+00:00')).astimezone(ZoneInfo(e.get('timezone') or 'America/New_York'))
 if start.date()<today:return None
 title=e['name'];url=e.get('external_url') or e['url']
 acts=parse_performers(title)
 source_artists=[n.strip() for n in e.get('artists',[]) if isinstance(n,str) and n.strip()]
 if source_artists:
  from concert_discovery.reconciliation import same_bill
  parsed=acts
  acts=[]
  for i,n in enumerate(source_artists):
   matches=[a for a in parsed if same_bill(a['name'],n)]
   # Prefer the billed spelling for a near-identical metadata name; use structured
   # names when the title includes extra tour/project wording.
   billed=next((a for a in matches if len(re.findall(r"[a-z0-9]+",a['name'].lower()))==len(re.findall(r"[a-z0-9]+",n.lower()))),None)
   acts.append(dict(name=billed['name'] if billed else n,role=matches[0]['role'] if matches else 'headliner_candidate' if i==0 else 'support',confidence=1,note='Structured DICE identity checked against billing.'))
 # A film accompanied by live music is billed by the score performer, not the film title.
 if not source_artists and re.search(r'\b(?:live\s+(?:metal\s+)?score|silent\s+film)\b',title,re.I):
  performer=re.search(r'(?:score\s+performed\s+by)\s+([^\n.]+)',e.get('raw_description',''),re.I)
  acts=[dict(name=performer[1].strip(),role='headliner',confidence=1,note='Explicit live-score performer attribution in official DICE description.')] if performer else []
 # Strip show-specific suffixes from performer identity while retaining full bill title.
 for a in acts:a['name']=re.sub(r'\s*[-–:]?\s*(?:\(?night\s+\d+\)?|\(?both nights\)?)\s*$','',a['name'],flags=re.I).strip().rstrip(' -–:')
 row=event('EulogyOfficial',url,title,start.strftime('%Y-%m-%d %H:%M:%S'),'eulogy',acts,url)
 row.update(event_status='cancelled' if cancelled else 'scheduled',category_text=title,official_event_url=url,date_status='venue_confirmed',date_note='Official Eulogy widget; timezone-adjusted DICE date.')
 if any(str(t).startswith('music:') for t in e.get('type_tags',[])):
  row['classifications']=[{'segment':{'name':'Music'}}]
 tickets=e.get('ticket_types') or []
 if tickets and all(t.get('sold_out') is True for t in tickets):row['ticket_availability']='sold_out'
 elif any(t.get('sold_out') is False for t in tickets):row['ticket_availability']='available'
 return row

def fetch_eulogy(session=None,today=None):
 session=session or requests.Session()
 r=session.get(PAGE,timeout=25);r.raise_for_status()
 m=re.search(r'DiceEventListWidget.create\((.*?)\);',r.text,re.S)
 if not m:raise ValueError('Eulogy widget configuration missing; completeness unconfirmed.')
 config=json.loads(m[1]);headers={'x-api-key':config['apiKey']}
 params=[('page[size]',24),('types','linkout,event')]+[('filter[promoters][]',p) for p in config['promoters']]
 url=ENDPOINT;rows=[];seen=set();pages=0
 for _ in range(10):
  r=session.get(url,params=params,headers=headers,timeout=25);r.raise_for_status();data=r.json();pages+=1
  if not isinstance(data.get('data'),list) or not isinstance(data.get('links'),dict):raise ValueError('Unexpected Eulogy page structure.')
  for item in data['data']:
   row=parse_event(item,today)
   if row and row['source_key'] not in seen:rows.append(row);seen.add(row['source_key'])
  next_url=data['links'].get('next')
  if not next_url:
   if not rows:raise ValueError('Empty Eulogy calendar; require review before retirement.')
   return rows,{'check_id':str(uuid.uuid4()),'venue_id':'eulogy','complete':True,'pages':pages,'event_keys':[e['source_key'] for e in rows],'source_url':PAGE}
  parsed=urlsplit(next_url)
  if parsed.hostname not in ('events-api.dice.fm','partners-endpoint.dice.fm') or parsed.path!='/api/v2/events':raise ValueError('Unexpected Eulogy pagination destination.')
  url=ENDPOINT+'?'+parsed.query;params=None
 raise ValueError('Eulogy pagination limit reached; completeness unconfirmed.')
