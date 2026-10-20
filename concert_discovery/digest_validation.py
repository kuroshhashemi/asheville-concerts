"""Conservative pre-send conflict detection; never deletes or merges shows."""
from datetime import datetime
from itertools import combinations
from concert_discovery.reconciliation import duplicate, is_official

def conflicts(selected, catalog, verified_pages=None):
    selected_ids={s['show_id'] for s in selected}
    issues=[]
    for a,b in combinations(catalog,2):
        if not selected_ids.intersection((a['show_id'],b['show_id'])):continue
        if a['venue_id']!=b['venue_id']:continue
        names=lambda s:{h.get('spotify_artist_id') or h.get('artist_id') or h['display_name'].casefold() for h in s.get('headliners',[])}
        na,nb=names(a),names(b)
        if not na or na!=nb:continue
        pages=verified_pages or {}
        # Independently matched official event pages substantiate separate dates.
        if (a['performance_start'][:10]!=b['performance_start'][:10]
            and pages.get(a['show_id']) and pages.get(b['show_id'])
            and pages[a['show_id']]!=pages[b['show_id']]):continue
        try:
            hours=abs((datetime.fromisoformat(a['performance_start'])-datetime.fromisoformat(b['performance_start'])).total_seconds())/3600
        except ValueError:continue
        # Nearby listings from aggregators can disagree on timezone or show time.
        # Explicit separate official performances remain valid, including multi-night runs.
        if duplicate(a,b,catalog) or (hours<=36 and not (is_official(a) and is_official(b))):
            issues.append({'show_ids':[a['show_id'],b['show_id']], 'reason':'Possible duplicate or conflicting date/time',
                           'title':a['title'],'times':[a['performance_start'],b['performance_start']]})
    return issues
