"""Validate browser filter preferences before durable storage."""
import math
VIEWS=('To Review','Hidden','Interested','Going','All')
def normalize(value,venues,genres,types,listener_max,growth_limits):
 value=value if isinstance(value,dict) else {}
 def omitted(key,allowed):
  candidates=value.get(key,[])
  return sorted(set(x for x in candidates if isinstance(x,str) and x in allowed)) if isinstance(candidates,list) else []
 def interval(key,limits):
  pair=value.get(key)
  if pair is None:return None
  if not isinstance(pair,(list,tuple)) or len(pair)!=2:return None
  if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in pair):return None
  low,high=sorted(max(limits[0],min(limits[1],int(x))) for x in pair)
  return None if (low,high)==tuple(limits) else [low,high]
 return dict(venue_grouping_version=1,review_view=value.get('review_view') if value.get('review_view') in VIEWS else 'To Review',
  excluded_venues=omitted('excluded_venues',venues),excluded_genres=omitted('excluded_genres',genres),excluded_types=omitted('excluded_types',types),
  hide_unknown=bool(value.get('hide_unknown',True)),listener_range=interval('listener_range',(0,listener_max)),growth_range=interval('growth_range',growth_limits),
  query=value.get('query','')[:200] if isinstance(value.get('query',''),str) else '')
