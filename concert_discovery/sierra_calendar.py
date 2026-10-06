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
