"""Hide recurring non-performance Events; never hide repeated artist shows."""
import re
from datetime import date

def exclusions(shows):
 groups={}
 for show in shows:
  if show['event_classification']['category']!='events':continue
  key=(show['venue_id'],re.sub(r'[^a-z0-9]','',show['title'].casefold()))
  groups.setdefault(key,[]).append(show)
 result={s['show_id']:'Explicitly identified recurring Events series: '+s['event_classification']['evidence'] for s in shows if s['event_classification']['category']=='events' and s['event_classification'].get('recurring_series')}
 for group in groups.values():
  days=sorted({date.fromisoformat(s['performance_start'][:10]) for s in group})
  if len(days)>=3 and (days[-1]-days[0]).days>=14:
   for show in group:result[show['show_id']]=f'Recurring Events series: {len(days)} dates at the same venue across {(days[-1]-days[0]).days} days'
 return result


def catalog_exclusions(c):
 from datetime import timedelta
 from concert_discovery.event_classification import category_for
 rows=[dict(r) for r in c.execute("SELECT * FROM shows WHERE substr(performance_start,1,10)>=?",((date.today()-timedelta(days=180)).isoformat(),))]
 for show in rows:show['event_classification']=category_for(c,show['show_id'],show['title'])
 return exclusions(rows)
