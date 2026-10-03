"""Show-first discovery and personal decisions, using cached metrics only."""
from datetime import date, datetime
import calendar
from concert_discovery.storage import connect,get_review_rows,utc_now

OWNER='local-owner'
def get_shows(db_path=None, user_id=OWNER):
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
        genres = {}
        icons={};images={}
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='artist_images'").fetchone():
            images={r['artist_id']:r['image_url'] for r in c.execute('SELECT i.* FROM artist_images i JOIN artists a USING(artist_id) WHERE i.source_url=a.spotify_profile_url')}
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='venue_icons'").fetchone():
            icons={r['venue_id']:r['icon_url'] for r in c.execute('SELECT * FROM venue_icons')}
        histories = {}
        for r in c.execute("""SELECT ms.artist_id,ms.retrieved_at,ms.monthly_listeners
            FROM artist_metric_snapshots ms JOIN artists a USING(artist_id)
            WHERE ms.status='success' AND ms.monthly_listeners IS NOT NULL
            AND ms.source_url=a.spotify_profile_url ORDER BY ms.retrieved_at"""):
            histories.setdefault(r['artist_id'],[]).append(dict(r))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artist_genres'").fetchone():
            genres = {r['artist_id']: r['genre'] for r in c.execute('SELECT artist_id,genre FROM artist_genres')}
    for s in shows:
        s['headliners']=headliners.get(s['show_id'],[])
        s['venue_icon']=icons.get(s['venue_id'])
        for a in s['headliners']:
            a['genre']=genres.get(a['artist_id']);a['image_url']=images.get(a['artist_id'])
        s['audience']=max((a['monthly_listeners'] for a in s['headliners'] if a['monthly_listeners'] is not None),default=None)
        s['audience_artist']=next((a for a in s['headliners'] if s['audience'] is not None and a['monthly_listeners']==s['audience']),None)
        for a in s['headliners']:
            a['listener_growth_6m']=six_month_growth(histories.get(a['artist_id'],[]))
        # One multi-artist show can surface when any headliner meets the growth filter.
        s['listener_growth_6m']=max((a['listener_growth_6m'] for a in s['headliners'] if a['listener_growth_6m'] is not None),default=None)
    return shows

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
    labels={None:'Unread','passed':'Pass','interested':'Interested'}
    return [s for s in shows if s['venue_name'] in venues
            and labels.get(s['decision'],'Unread') in statuses
            and (minimum==0 or (s['audience'] is not None and s['audience']>=minimum))
            and (minimum_growth is None or (s.get('listener_growth_6m') is not None and s['listener_growth_6m']>=minimum_growth))]

def compact_audience(value):
    if value is None:return '—'
    if value>=1000:return f'{round(value/1000):,}k'
    return str(value)
