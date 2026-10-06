"""Show-first discovery and personal decisions, using cached metrics only."""
from datetime import date, datetime
import calendar, re
from concert_discovery.storage import connect,get_review_rows,utc_now

OWNER='local-owner'
def get_shows(db_path=None, user_id=OWNER, include_recurring=False):
    artists=get_review_rows(db_path); headliners={}
    for a in artists:
        for s in a['shows']:
            if 'headliner' in s['billing_role']:
                headliners.setdefault(s['show_id'],[]).append(a)
    with connect(db_path) as c:
        shows=[dict(r) for r in c.execute("""SELECT s.*,v.name venue_name,d.decision
           FROM shows s JOIN venues v USING(venue_id)
           LEFT JOIN user_show_decisions d ON d.show_id=s.show_id AND d.user_id=?
           WHERE substr(s.performance_start,1,10)>=? ORDER BY performance_start""",(user_id,date.today().isoformat()))]
        from concert_discovery.event_classification import schema as category_schema,EXCLUDED
        category_schema(c)
        from concert_discovery.event_classification import category_for,effective
        from concert_discovery.reconciliation import schema as alias_schema
        alias_schema(c)
        aliases={r[0] for r in c.execute('SELECT alias_id FROM show_aliases')}
        categories={s['show_id']:category_for(c,s['show_id'],s['title']) for s in shows}
        category_exclusions={sid for sid,r in categories.items() if r['category'] in EXCLUDED}
        cancelled=set()
        for show in shows:
            state=effective(c,'show_event_states',show['show_id'])
            if (state and state['status']=='cancelled') or (not state and re.search(r'\bcancell?ed\b',show['title'],re.I)):cancelled.add(show['show_id'])
        retired={r[0] for r in c.execute('SELECT show_id FROM calendar_presence WHERE misses>=2')}
        reviewed_exclusions={r[0] for r in c.execute('SELECT show_id FROM show_review_exclusions')}
        c.execute("CREATE TABLE IF NOT EXISTS show_discovery(show_id INTEGER PRIMARY KEY,first_seen_at TEXT,eligible INTEGER)")
        # Existing catalog is a baseline, never retroactively called just announced.
        c.execute("INSERT OR IGNORE INTO show_discovery SELECT show_id,?,0 FROM shows",(utc_now(),))
        announcements={r[0]:r[1] for r in c.execute("SELECT show_id,first_seen_at FROM show_discovery WHERE eligible=1 AND julianday(first_seen_at)>=julianday('now','-7 days')")}
        c.execute('CREATE TABLE IF NOT EXISTS artist_entity_types(name_key TEXT PRIMARY KEY,kind TEXT,evidence TEXT)')
        entity_types={r[0]:r[1] for r in c.execute('SELECT name_key,kind FROM artist_entity_types')}
        availability={}
        for r in c.execute("SELECT * FROM ticket_availability WHERE status='sold_out'"):
            availability.setdefault(r['show_id'],dict(r))
        genres = {}; genre_sources={};image_sources={};sources={}
        icons={};images={}
        for r in c.execute('SELECT * FROM show_sources ORDER BY source_name'):
            sources.setdefault(r['show_id'],[]).append(dict(r))
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='artist_images'").fetchone():
            images={r['artist_id']:r['image_url'] for r in c.execute('SELECT i.* FROM artist_images i JOIN artists a USING(artist_id) WHERE i.source_url=a.spotify_profile_url')}
        image_sources={r['artist_id']:r['source_url'] for r in c.execute('SELECT * FROM artist_images')}
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='venue_icons'").fetchone():
            icons={r['venue_id']:r['icon_url'] for r in c.execute('SELECT * FROM venue_icons')}
        from concert_discovery.pastspot import schema, comparison
        schema(c)
        provider_history={}
        for r in c.execute("SELECT * FROM listener_history"):
            provider_history.setdefault(r["spotify_id"],[]).append(dict(r))
        histories = {}
        for r in c.execute("""SELECT ms.artist_id,ms.retrieved_at,ms.monthly_listeners
            FROM artist_metric_snapshots ms JOIN artists a USING(artist_id)
            WHERE ms.status='success' AND ms.monthly_listeners IS NOT NULL
            AND ms.source_url=a.spotify_profile_url ORDER BY ms.retrieved_at"""):
            histories.setdefault(r['artist_id'],[]).append(dict(r))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artist_genres'").fetchone():
            genres = {r['artist_id']: r['genre'] for r in c.execute("SELECT artist_id,genre FROM artist_genres WHERE source_url LIKE 'https://www.jambase.com/%' OR source_url LIKE 'https://jambase.com/%'")}
            genre_sources={r['artist_id']:r['source_url'] for r in c.execute('SELECT * FROM artist_genres')}
    shows=[s for s in shows if s['show_id'] not in aliases and s['show_id'] not in retired and s['show_id'] not in cancelled and s['show_id'] not in category_exclusions and s['show_id'] not in reviewed_exclusions]
    for s in shows:
        s['just_announced']=announcements.get(s['show_id'])
        # Apostrophe typography from different providers must not duplicate a performer.
        from concert_discovery.spotify_matching import name_key
        unique={}
        for a in headliners.get(s['show_id'],[]):
            key=name_key(a['display_name'])
            if key not in unique or (a.get('spotify_artist_id') and not unique[key].get('spotify_artist_id')):unique[key]=a
        headliners[s['show_id']]=list(unique.values())
        s['event_classification']=categories.get(s['show_id'])
        s['sold_out']=availability.get(s['show_id'])
        s['sources']=sources.get(s['show_id'],[])
        s['headliners']=headliners.get(s['show_id'],[])
        # Keep the bill's written order; audience size never rearranges performers.
        from concert_discovery.event_sources import parse_performers
        from concert_discovery.reconciliation import same_bill
        bill=[p['name'] for p in parse_performers(s['title'])]
        def billing_order(a):
            title_key=name_key(s['title']);artist_key=name_key(a['display_name'])
            position=title_key.find(artist_key)
            if position>=0:return position
            matches=[title_key.find(name_key(name)) for name in bill if same_bill(name,a['display_name'])]
            return min(matches) if matches else len(title_key)
        s['headliners'].sort(key=billing_order)
        from concert_discovery.bill_presentation import performers
        s['headliners']=performers(s['headliners'],s['title'])
        s['venue_icon']=icons.get(s['venue_id'])
        for a in s['headliners']:
            a['entity_kind']=entity_types.get(name_key(a['display_name']),'artist')
            if a['entity_kind']!='artist':
                a['spotify_artist_id']=None;a['spotify_profile_url']=None;a['monthly_listeners']=None
            a['genre']=genres.get(a['artist_id']);a['image_url']=images.get(a['artist_id']);a['genre_source']=genre_sources.get(a['artist_id']);a['image_source']=image_sources.get(a['artist_id'])
        s['audience']=max((a['monthly_listeners'] for a in s['headliners'] if a['monthly_listeners'] is not None),default=None)
        s['audience_artist']=next((a for a in s['headliners'] if s['audience'] is not None and a['monthly_listeners']==s['audience']),None)
        for a in s['headliners']:
            a['growth_detail']=comparison(provider_history.get(a['spotify_artist_id'],[]))
            a['listener_growth_6m']=a['growth_detail']['value'] if a['growth_detail'] else six_month_growth(histories.get(a['artist_id'],[]))
        # One multi-artist show can surface when any headliner meets the growth filter.
        s['growth_artist']=max((a for a in s['headliners'] if a['listener_growth_6m'] is not None),key=lambda a:a['listener_growth_6m'],default=None)
        s['listener_growth_6m']=max((a['listener_growth_6m'] for a in s['headliners'] if a['listener_growth_6m'] is not None),default=None)
    from concert_discovery.reconciliation import reconcile
    shows=reconcile(shows)
    from concert_discovery.recurring_events import catalog_exclusions
    with connect(db_path) as c:recurring=catalog_exclusions(c)
    return shows if include_recurring else [s for s in shows if s['show_id'] not in recurring]

def six_month_growth(history):
    """Same-profile measured growth; baseline within 14 days of six calendar months.

    Never substitute a short observation window or zero for unavailable history.
    """
    observations=[]
    for row in history:
        try:
            day=datetime.fromisoformat(row['retrieved_at'].replace('Z','+00:00')).date()
            count=row['monthly_listeners']
            if isinstance(count,int) and count>=0: observations.append((day,count))
        except (ValueError,TypeError): continue
    if not observations:return None
    latest,count=max(observations,key=lambda x:x[0])
    month_index=latest.year*12+latest.month-1-6
    year,month=divmod(month_index,12);month+=1
    target=date(year,month,min(latest.day,calendar.monthrange(year,month)[1]))
    candidates=[(day,n) for day,n in observations if n>0 and abs((day-target).days)<=14]
    if not candidates:return None
    _,baseline=min(candidates,key=lambda x:abs((x[0]-target).days))
    return (count/baseline-1)*100

def decide(show_id,decision,db_path=None, user_id=OWNER):
    if decision not in ('interested','passed',None):raise ValueError('Invalid decision')
    with connect(db_path) as c:
        if decision is None:
            c.execute('DELETE FROM user_show_decisions WHERE user_id=? AND show_id=?',(user_id,show_id))
        else:
            c.execute('''INSERT INTO user_show_decisions(user_id,show_id,decision,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(user_id,show_id) DO UPDATE SET decision=excluded.decision,updated_at=excluded.updated_at''',(user_id,show_id,decision,utc_now()))

def select_shows(shows,view='Shortlist',minimum=250000,venue='All venues',hide_passed=True):
    return [s for s in shows if (venue=='All venues' or s['venue_name']==venue)
            and (not hide_passed or s['decision']!='passed')
            and (view!='Interested' or s['decision']=='interested')
            and (view!='Shortlist' or (s['audience'] is not None and s['audience']>=minimum))]


def filter_table(shows,venues,statuses,minimum=0,minimum_growth=None):
    """Explicit multi-selects; no minimum retains unknown audience."""
    labels={None:'Unread','passed':'Pass','interested':'Interested','going':'Going'}
    return [s for s in shows if s['venue_name'] in venues
            and labels.get(s['decision'],'Unread') in statuses
            and (minimum==0 or (s['audience'] is not None and s['audience']>=minimum))
            and (minimum_growth is None or (s.get('listener_growth_6m') is not None and s['listener_growth_6m']>=minimum_growth))]

def compact_audience(value):
    if value is None:return '—'
    if value>=1000:return f'{round(value/1000):,}k'
    return "< 1k"


def exclusion_label(reason):
    text=reason.casefold()
    if 'recurring' in text:return 'Recurring event'
    if text.startswith('duplicate'):return 'Duplicate'
    if text.startswith('absent'):return 'No longer listed'
    if text.startswith('cancel'):return 'Cancelled'
    if text.startswith('reviewed'):return 'Reviewed exclusion'
    return reason.split(':',1)[0]

def excluded_events(db_path=None):
    """Stored upcoming listings withheld by catalog rules, independent of UI filters."""
    from concert_discovery.event_classification import category_for,effective,EXCLUDED
    with connect(db_path) as c:
        aliases={r[0] for r in c.execute('SELECT alias_id FROM show_aliases')}
        retired={r[0] for r in c.execute('SELECT show_id FROM calendar_presence WHERE misses>=2')}
        reviews={r['show_id']:dict(r) for r in c.execute('SELECT * FROM show_review_exclusions')}
        out=[]
        for r in c.execute("SELECT s.*,v.name venue FROM shows s JOIN venues v USING(venue_id) WHERE substr(performance_start,1,10)>=? ORDER BY performance_start",(date.today().isoformat(),)).fetchall():
            sid=r['show_id'];category=category_for(c,sid,r['title']);state=effective(c,'show_event_states',sid);reasons=[]
            if category['category'] in EXCLUDED:reasons.append(category['category'].replace('_',' ').title()+': '+category['evidence'])
            if sid in aliases:reasons.append('Duplicate listing merged into another show')
            if sid in retired:reasons.append('Absent from two complete official-calendar checks')
            if (state and state['status']=='cancelled') or (not state and re.search(r'\bcancell?ed\b',r['title'],re.I)):reasons.append('Cancelled')
            if sid in reviews:reasons.append('Reviewed exclusion: '+reviews[sid]['reason'])
            if reasons:
                source=c.execute('SELECT source_url FROM show_sources WHERE show_id=? ORDER BY source_name LIMIT 1',(sid,)).fetchone()
                out.append({'Date':r['performance_start'][:10],'Event':r['title'],'Venue':r['venue'],'Reason':'; '.join(reasons),'Source':source[0] if source else ''})
        from concert_discovery.recurring_events import exclusions
        candidates=[dict(r) for r in c.execute("SELECT s.*,v.name venue_name FROM shows s JOIN venues v USING(venue_id) WHERE substr(performance_start,1,10)>=?",(date.today().isoformat(),))]
        for show in candidates:show['event_classification']=category_for(c,show['show_id'],show['title'])
        from concert_discovery.recurring_events import catalog_exclusions
        recurring=catalog_exclusions(c)
        listed={row['Event']+row['Date'] for row in out}
        for show in candidates:
            if show['show_id'] not in recurring or show['title']+show['performance_start'][:10] in listed:continue
            source=c.execute('SELECT source_url FROM show_sources WHERE show_id=? LIMIT 1',(show['show_id'],)).fetchone()
            out.append({'Date':show['performance_start'][:10],'Event':show['title'],'Venue':show['venue_name'],'Reason':recurring[show['show_id']],'Source':source[0] if source else ''})
        for row in out:
            row['Reason']=' · '.join(dict.fromkeys(exclusion_label(reason) for reason in row['Reason'].split('; ')))
        return sorted(out,key=lambda r:r['Date'])
