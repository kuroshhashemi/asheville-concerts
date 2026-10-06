"""Faceted event counts: apply all active filters except the counted category."""
def counts(shows,venues,genres,types,statuses,listener_range,hide_unknown,growth_range,growth_limits,query,show_genres):
 result={k:{} for k in ('venue','genre','type','status')};totals={k:0 for k in result}
 query=query.strip().casefold()
 decisions={None:'Unread','passed':'Pass','interested':'Interested','going':'Going'}
 low,high=listener_range;glow,ghigh=growth_range
 for show in shows:
  audience=show['audience'];growth=show['listener_growth_6m']
  if audience is None:
   if hide_unknown or low>0:continue
  elif not low*1000<=audience<=high*1000:continue
  if growth_range!=growth_limits and (growth is None or not glow<=growth<=ghigh):continue
  if query and query not in show['title'].casefold() and not any(query in a['display_name'].casefold() for a in show['headliners']):continue
  values={'venue':{show['venue_name']},'genre':show_genres(show),'type':{show['event_classification']['category'].replace('_',' ').title()},'status':{decisions.get(show['decision'],'Unread')}}
  selected={'venue':set(venues),'genre':set(genres),'type':set(types),'status':set(statuses)}
  for facet in result:
   if all(values[k]&selected[k] for k in values if k!=facet):
    totals[facet]+=1
    for value in values[facet]:result[facet][value]=result[facet].get(value,0)+1
 return result,totals
