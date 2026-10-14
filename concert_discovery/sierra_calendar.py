"""Parse Sierra event cards with explicit location and case-insensitive dates."""
import re
from datetime import date,datetime,timedelta
from concert_discovery.api_sources import event
from concert_discovery.event_sources import parse_performers

def parse_cards(cards,today=None,days=None):
 today=today or date.today();end=today+timedelta(days=days) if days is not None else date.max
 rows=[]
 for card in cards:
  text=card.get('text','');title=card.get('title');url=card.get('url')
  # Chico and unknown locations must never be silently assigned to Mills River.
  if not re.search(r'\bMills River\b',text,re.I):continue
  match=re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,?\s+(20\d\d))?',text,re.I)
  if not match or not title or not url:raise ValueError('Unparsed Mills River calendar card; no completeness snapshot')
  month=datetime.strptime(match[1].title(),'%B').month
  year=int(match[3]) if match[3] else today.year+(month<today.month)
  day=date(year,month,int(match[2]))
  if not today<=day<=end:continue
  tm=re.search(r'\b(\d{1,2}):(\d{2})\s*(AM|PM)\b',text,re.I)
  start=day.isoformat()
  if tm:start+=f' {int(tm[1])%12+(12 if tm[3].upper()=="PM" else 0):02d}:{tm[2]}:00'
  row=event('SierraOfficial',url,title,start,'sierra-nevada',parse_performers(title),url)
  row.update(official_event_url=url,date_status='venue_confirmed',category_text=text,event_status='cancelled' if re.search(r'\bcancell?ed\b',text,re.I) else 'scheduled')
  from concert_discovery.availability import text_availability
  row['ticket_availability']=text_availability(text)
  rows.append(row)
 if not rows:raise ValueError('No upcoming Mills River event cards; retain prior catalog')
 return rows

API_URL='https://webadmin.sierranevada.com/wp-json/tribe/events/v1/events'

def reconcile_urls(events,db_path=None):
 """An unambiguous artist/date/venue link can share official admission evidence.

 Keeps records, dates and titles intact; never spreads a price across different
 nights or venues, and does not guess when multiple official events match.
 """
 from concert_discovery.storage import connect
 from concert_discovery.prices import load,url_key
 official=[e for e in events if e.get('source_name')=='SierraOfficial'];prices=load()
 with connect(db_path) as c:
  for s in c.execute("SELECT show_id,title,performance_start,official_event_url FROM shows WHERE venue_id='sierra-nevada'").fetchall():
   if s['official_event_url']:continue
   names=[r[0] for r in c.execute('SELECT a.display_name FROM artists a JOIN show_artists sa USING(artist_id) WHERE sa.show_id=? AND sa.billing_role LIKE ?', (s['show_id'],'%headliner%'))]
   candidates=[e for e in official if e['performance_start'][:10]==s['performance_start'][:10] and any(n.casefold() in e['title'].casefold() for n in names if len(n)>=5)]
   if len(candidates)==1 and url_key(candidates[0]['official_event_url']) in prices:
    c.execute('UPDATE shows SET official_event_url=? WHERE show_id=?',(candidates[0]['official_event_url'],s['show_id']))

def parse_api(data,today=None):
 import html
 from concert_discovery.prices import structured,advertised
 today=today or date.today();rows=[]
 for item in data.get('events',[]):
  venue=item.get('venue') or {}
  city=str(venue.get('city','')).casefold()
  explicit_mills=city=='mills river' or (not city and ('/mills-river/' in venue.get('url','') or re.search(r'\bMills River\b',html.unescape(item.get('title','')),re.I)))
  if not explicit_mills:continue
  start=item.get('start_date','')
  if not start or date.fromisoformat(start[:10])<today:continue
  title=html.unescape(item['title']);url=item['url']
  row=event('SierraOfficial',url,title,start,'sierra-nevada',parse_performers(title),item.get('website') or url)
  description=re.sub('<[^>]+>',' ',html.unescape(item.get('description','')))
  row.update(official_event_url=url,date_status='venue_confirmed',category_text=description,
             advertised_price=structured(item) or advertised(title+'\n'+description),event_status='cancelled' if item.get('event_status') in ('cancelled','canceled') else 'scheduled')
  rows.append(row)
 return rows

def fetch_api(snapshots=None):
 import requests
 rows=[];total=None;seen=0
 for page in range(1,21):
  r=requests.get(API_URL,params={'start_date':date.today().isoformat(),'per_page':100,'page':page},timeout=25);r.raise_for_status();data=r.json()
  if total is None:total=int(data['total']);pages=int(data['total_pages'])
  seen+=len(data.get('events',[]))
  rows.extend(parse_api(data))
  if page>=pages:
   if seen!=total:raise ValueError('Sierra pagination count mismatch; no completeness snapshot')
   if snapshots is not None and rows:
    from concert_discovery.calendar_audit import snapshots as make_snapshots
    snapshots.extend(make_snapshots(rows,'https://sierranevada.com/events',page))
   return rows
 raise ValueError('Sierra calendar exceeded bounded pagination; no completeness snapshot')
