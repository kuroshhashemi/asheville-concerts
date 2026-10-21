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

def queue_schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS growth_queue (spotify_id TEXT PRIMARY KEY, reason TEXT NOT NULL, updated_at TEXT NOT NULL)')

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
    if (today-latest).days>104:return None
    y,m=divmod(latest.year*12+latest.month-1-6,12);m+=1
    target=date(y,m,min(latest.day,calendar.monthrange(y,m)[1]))
    candidates=[r for r in valid if abs((r[0]-target).days)<=14]
    if not candidates:return None
    baseline,n,_=min(candidates,key=lambda r:abs((r[0]-target).days))
    if n==0:return None
    return dict(value=(count/n-1)*100,baseline_date=baseline.isoformat(),latest_date=latest.isoformat(),source_url=url)

def due(row, force=False, now=None):
    if not row.get('checked_at'):return True
    now=now or datetime.now().astimezone()
    checked=datetime.fromisoformat(row['checked_at'].replace('Z','+00:00'))
    days=(now-checked).total_seconds()/86400
    # Even digest final retries must respect successful 90-day caching.
    interval=90 if row.get('status') in ('history','not_found','no_history') else 1
    return days>=interval or (force and interval==1)

def refresh_history(db_path=None, limit=40, spotify_ids=None, force=False, priority_ids=None, allow_brightdata=True):
    """Cache successful/unavailable history for 90 days; failures retry daily."""
    with connect(db_path) as c:
        schema(c)
        artists=[dict(r) for r in c.execute('''SELECT DISTINCT a.spotify_artist_id,h.checked_at,h.status
          FROM artists a JOIN show_artists sa USING(artist_id) JOIN shows s USING(show_id)
          LEFT JOIN show_discovery d USING(show_id)
          LEFT JOIN history_checks h ON h.spotify_id=a.spotify_artist_id
          WHERE a.spotify_artist_id IS NOT NULL AND s.performance_start>=?
          AND sa.billing_role LIKE '%headliner%'
          GROUP BY a.spotify_artist_id
          ORDER BY h.checked_at IS NOT NULL, COALESCE(h.checked_at,''), a.spotify_artist_id''',(date.today().isoformat(),))]
    from concert_discovery.discovery import get_shows
    visible={a['spotify_artist_id'] for show in get_shows(db_path) for a in show['headliners'] if a.get('spotify_artist_id')}
    artists=[a for a in artists if a['spotify_artist_id'] in visible]
    if spotify_ids is not None:artists=[a for a in artists if a['spotify_artist_id'] in spotify_ids]
    if priority_ids:artists.sort(key=lambda a:a['spotify_artist_id'] not in priority_ids)
    artists=[a for a in artists if due(a,force=force)]
    stop_reason='Daily batch limit reached'
    with connect(db_path) as c:
        queue_schema(c)
        c.executemany('INSERT OR REPLACE INTO growth_queue VALUES(?,?,?)',[(a['spotify_artist_id'],'Queued for growth check',utc_now()) for a in artists])
    attempted=0
    provider_status='available'
    for a in artists:
        if attempted>=limit:break
        sid=a['spotify_artist_id'];url='https://pastspot.com/artists/'+sid
        attempted+=1
        try:
            response=requests.get(url,timeout=15)
            if response.status_code in (403,429) and allow_brightdata:
                from concert_discovery.api_sources import secret
                from concert_discovery.brightdata_guard import reserve_growth
                key=secret('BRIGHTDATA_API_KEY');zone=secret('BRIGHTDATA_UNLOCKER_ZONE')
                allowed,guard_reason=reserve_growth(db_path) if key and zone else (False,'Bright Data credentials unavailable')
                if not allowed:stop_reason=guard_reason
                if allowed:
                    response=requests.post('https://api.brightdata.com/request',headers={'Authorization':'Bearer '+key},json={'zone':zone,'url':url,'format':'raw'},timeout=60)
            if response.status_code in (403,429):
                save(sid,[],url,'blocked' if response.status_code==403 else 'rate_limited',db_path)
                provider_status='blocked' if response.status_code==403 else 'rate_limited'
                if not (allow_brightdata and 'guard_reason' in locals() and not allowed):stop_reason='Provider blocked requests' if response.status_code==403 else 'Provider rate limit reached'
                break
            response.raise_for_status()
            html=response.text.replace('\\"','"')
            pairs=set((d,int(n)) for d,n in re.findall(r'"periodStartDate":"(\d{4}-\d{2}-\d{2})"[^}]*?"monthlyListeners":(\d+)',html))
            by_day={}
            for day,n in pairs:by_day.setdefault(day,set()).add(n)
            if any(len(n)>1 for n in by_day.values()):
                save(sid,[],url,'parse_error',db_path);continue
            save(sid,[dict(date=d,listeners=n) for d,n in sorted(pairs)],url,
                 'not_found' if 'Artist Not Found' in html else 'history' if pairs else 'no_history' if 'Monthly Listeners' in html else 'parse_error',db_path)
        except requests.RequestException:
            save(sid,[],url,'request_error',db_path);continue
        time.sleep(.3)
    with connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS growth_provider_checks (provider TEXT PRIMARY KEY,status TEXT,checked_at TEXT,detail TEXT)')
        if attempted:c.execute('INSERT OR REPLACE INTO growth_provider_checks VALUES(?,?,?,?)',('pastspot',provider_status,utc_now(),stop_reason if provider_status!='available' else 'Batch completed without an access block'))
        for a in artists[:attempted]:c.execute('DELETE FROM growth_queue WHERE spotify_id=?',(a['spotify_artist_id'],))
        c.executemany('UPDATE growth_queue SET reason=?,updated_at=? WHERE spotify_id=?',[(stop_reason,utc_now(),a['spotify_artist_id']) for a in artists[attempted:]])
    return {'history_requests':attempted,'history_queued':len(artists)-attempted,'history_provider_status':provider_status if attempted else 'not_checked','history_stop_reason':stop_reason if len(artists)>attempted else None}
