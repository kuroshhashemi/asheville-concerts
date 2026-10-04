"""Free dated listener history, kept separate from live Spotify observations."""
import calendar, json, re, time
from datetime import date, datetime, timedelta
import requests
from concert_discovery.storage import connect, utc_now

def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS listener_history (
      spotify_id TEXT NOT NULL, observed_date TEXT NOT NULL, listeners INTEGER NOT NULL,
      source_url TEXT NOT NULL, imported_at TEXT NOT NULL,
      PRIMARY KEY(spotify_id,observed_date))''')
    c.execute('''CREATE TABLE IF NOT EXISTS history_checks (
      spotify_id TEXT PRIMARY KEY, checked_at TEXT NOT NULL, status TEXT NOT NULL)''')

def save(spotify_id, observations, source_url, status, db_path=None):
    with connect(db_path) as c:
        schema(c)
        c.executemany('INSERT OR REPLACE INTO listener_history VALUES(?,?,?,?,?)',
          [(spotify_id,r['date'],r['listeners'],source_url,utc_now()) for r in observations])
        c.execute('INSERT OR REPLACE INTO history_checks VALUES(?,?,?)',(spotify_id,utc_now(),status))

def comparison(rows, today=None):
    today=today or date.today()
    valid=sorted((date.fromisoformat(r['observed_date']),r['listeners'],r['source_url']) for r in rows
      if isinstance(r['listeners'],int) and r['listeners']>=0 and date.fromisoformat(r['observed_date'])<=today)
    if not valid:return None
    latest,count,url=valid[-1]
    if (today-latest).days>14:return None
    y,m=divmod(latest.year*12+latest.month-1-6,12);m+=1
    target=date(y,m,min(latest.day,calendar.monthrange(y,m)[1]))
    candidates=[r for r in valid if abs((r[0]-target).days)<=14]
    if not candidates:return None
    baseline,n,_=min(candidates,key=lambda r:abs((r[0]-target).days))
    if n==0:return None
    return dict(value=(count/n-1)*100,baseline_date=baseline.isoformat(),latest_date=latest.isoformat(),source_url=url)

def refresh_history(db_path=None, limit=40):
    """Bounded weekly checks; missing artists retry after 30 days. No UI requests."""
    with connect(db_path) as c:
        schema(c)
        artists=[dict(r) for r in c.execute('''SELECT DISTINCT a.spotify_artist_id,h.checked_at,h.status
          FROM artists a JOIN show_artists sa USING(artist_id) JOIN shows s USING(show_id)
          LEFT JOIN history_checks h ON h.spotify_id=a.spotify_artist_id
          WHERE a.spotify_artist_id IS NOT NULL AND s.performance_start>=?
          AND sa.billing_role LIKE '%headliner%' ORDER BY COALESCE(h.checked_at,'')''',(date.today().isoformat(),))]
    attempted=0
    for a in artists:
        if a['checked_at']:
            age=(datetime.now().date()-datetime.fromisoformat(a['checked_at'].replace('Z','+00:00')).date()).days
            if age<(30 if a['status']=='not_found' else 7):continue
        if attempted>=limit:break
        sid=a['spotify_artist_id'];url='https://pastspot.com/artists/'+sid
        attempted+=1
        try:
            response=requests.get(url,timeout=15)
            if response.status_code in (403,429):break
            response.raise_for_status()
            html=response.text.replace('\\"','"')
            pairs=set((d,int(n)) for d,n in re.findall(r'"periodStartDate":"(\d{4}-\d{2}-\d{2})"[^}]*?"monthlyListeners":(\d+)',html))
            by_day={}
            for day,n in pairs:by_day.setdefault(day,set()).add(n)
            if any(len(n)>1 for n in by_day.values()):continue
            save(sid,[dict(date=d,listeners=n) for d,n in sorted(pairs)],url,
                 'not_found' if 'Artist Not Found' in html else 'history' if pairs else 'no_history',db_path)
        except requests.RequestException:continue
        time.sleep(.3)
    return {'history_requests':attempted}
