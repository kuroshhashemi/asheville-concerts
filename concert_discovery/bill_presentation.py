"""Display a full event title, or one identity per performer/project."""
import re
from concert_discovery.event_sources import strip_billing_prefix

def project_key(name):
 name=re.sub(r"\s+(?:&|and)\s+friends\b.*$",'',name,flags=re.I)
 name=re.sub(r"\s*[-–—:]\s*(?:the\s+)?(?:ultimate\s+)?[^–—:]*\b(?:tribute|experience)\b.*$",'',name,flags=re.I)
 return re.sub(r'[^a-z0-9]','',name.casefold())

def canonical_billing_name(label,title):
 from concert_discovery.event_sources import parse_performers
 from concert_discovery.reconciliation import same_bill
 names=[p['name'] for p in parse_performers(title)]
 matches=[n for n in names if same_bill(n,label)]
 return matches[0] if len(matches)==1 else label

def performers(artists,title):
 groups={}
 for a in artists:groups.setdefault(project_key(a['display_name']),[]).append(a)
 out=[]
 for group in groups.values():
  profiles={a.get('spotify_artist_id') for a in group if a.get('spotify_artist_id')}
  if len(profiles)>1:out.extend(group);continue
  preferred=min(group,key=lambda a:(not bool(a.get('spotify_artist_id')),len(a['display_name'])))
  out.append(preferred)
 # Drop an unmatched combined billing label only when every named performer
 # already exists separately. Never split a confirmed band (e.g. Earth, Wind & Fire).
 # Reject a search-only alternate spelling when the bill explicitly names
 # a separately present performer. Different verified Spotify identities remain distinct.
 present={project_key(a['display_name']) for a in out}
 out=[a for a in out if not (a.get('match_status')=='candidate'
  and 'official Spotify search' in a.get('match_reason','')
  and project_key(canonical_billing_name(a['display_name'],title))!=project_key(a['display_name'])
  and project_key(canonical_billing_name(a['display_name'],title)) in present)]
 keys={project_key(a['display_name']) for a in out}
 return [a for a in out if a.get('spotify_artist_id') or not (
  len(parts:=re.split(r'\s+(?:&|and)\s+',a['display_name'],flags=re.I))>1
  and all(project_key(part) in keys for part in parts))]

def name(show):
 kind=show['event_classification']['category']
 if kind not in ('live_music','cover_band'):return show['title']
 acts=show['headliners']
 return ' & '.join(dict.fromkeys(a['display_name'] for a in acts)) if acts else strip_billing_prefix(show['title'])
