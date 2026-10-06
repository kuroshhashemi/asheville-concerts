"""Display a full event title, or one identity per performer/project."""
import re
from concert_discovery.event_sources import strip_billing_prefix

def project_key(name):
 name=re.sub(r"\s+(?:&|and)\s+friends\b.*$",'',name,flags=re.I)
 name=re.sub(r"\s*[-–—:]\s*(?:the\s+)?(?:ultimate\s+)?[^–—:]*\b(?:tribute|experience)\b.*$",'',name,flags=re.I)
 return re.sub(r'[^a-z0-9]','',name.casefold())

def performers(artists,title):
 groups={}
 for a in artists:groups.setdefault(project_key(a['display_name']),[]).append(a)
 out=[]
 for group in groups.values():
  profiles={a.get('spotify_artist_id') for a in group if a.get('spotify_artist_id')}
  if len(profiles)>1:out.extend(group);continue
  preferred=min(group,key=lambda a:(not bool(a.get('spotify_artist_id')),len(a['display_name'])))
  out.append(preferred)
 return out

def name(show):
 kind=show['event_classification']['category']
 if kind not in ('live_music','cover_band'):return show['title']
 acts=show['headliners']
 return ' & '.join(dict.fromkeys(a['display_name'] for a in acts)) if acts else strip_billing_prefix(show['title'])
