"""Scheduled shared-catalog refresh; personal decisions are never exported."""
import json, re, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import requests
from concert_discovery.storage import initialize,connect,upsert_show,upsert_artist,utc_now,DATABASE_PATH
from concert_discovery.official_calendar import fetch_all_calendars
from concert_discovery.api_sources import fetch_jambase,fetch_ticketmaster
from concert_discovery.collector import collect_artist_metric

def save_events(events,db_path=DATABASE_PATH):
    with connect(db_path) as c:
        for e in events:
            if not e.get('venue_id') or not e.get('performers'):continue
            upsert_show(c,e)
            for name,metadata in e.get('artist_metadata',{}).items():
                aid=upsert_artist(c,name)
                genre=metadata.get('genre')
                if genre and genre.lower() not in ('undefined','music'):
                    c.execute('INSERT INTO artist_genres(artist_id,genre,source_url) VALUES(?,?,?) ON CONFLICT(artist_id) DO UPDATE SET genre=excluded.genre,source_url=excluded.source_url',(aid,genre,e['source_url']))

def enrich(limit=40,db_path=DATABASE_PATH):
    with connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS identity_attempts(artist_id TEXT PRIMARY KEY,checked_at TEXT)')
        artists=[dict(r) for r in c.execute("""SELECT DISTINCT a.* FROM artists a JOIN show_artists sa USING(artist_id) JOIN shows s USING(show_id)
            WHERE sa.billing_role LIKE '%headliner%' AND substr(s.performance_start,1,10)>=date('now')
            ORDER BY a.spotify_artist_id IS NULL,s.performance_start""")]
    attempted=0;good=0
    for a in artists:
        if attempted>=limit:break
        with connect(db_path) as c:
            fresh=c.execute("SELECT 1 FROM artist_metric_snapshots WHERE artist_id=? AND status='success' AND source_url=? AND retrieved_at>=?",(a['artist_id'],a['spotify_profile_url'],(datetime.now(timezone.utc)-timedelta(days=7)).isoformat())).fetchone()
            recent=c.execute("SELECT 1 FROM identity_attempts WHERE artist_id=? AND checked_at>=?",(a['artist_id'],(datetime.now(timezone.utc)-timedelta(days=7)).isoformat())).fetchone()
        if fresh or (not a['spotify_artist_id'] and recent):continue
        attempted+=1
        if not a['spotify_artist_id']:
            with connect(db_path) as c:c.execute('INSERT OR REPLACE INTO identity_attempts VALUES(?,?)',(a['artist_id'],utc_now()))
            try:
                response=requests.get('https://rest.bandsintown.com/artists/'+quote(a['display_name'],safe=''),params={'app_id':'js_127.0.0.1'},timeout=15)
                response.raise_for_status();artist=response.json()
                norm=lambda s:re.sub(r'[^a-z0-9]','',s.casefold())
                if norm(artist.get('name',''))!=norm(a['display_name']):continue
                links=artist.get('links',[])
                sid=next((m[1] for link in links if (m:=re.search(r'open.spotify.com/artist/([A-Za-z0-9]{22})',link.get('url','')))),None)
                if not sid:continue
                with connect(db_path) as c:upsert_artist(c,a['display_name'],sid,'Linked from matching Bandsintown artist profile; Spotify name checked during metric retrieval.')
            except (requests.RequestException,ValueError,TypeError):continue
        result=collect_artist_metric(a['artist_id'],db_path)
        good+=result['status']=='success'
        if result['status'] in ('blocked','rate_limited'):break
    return {'attempted':attempted,'metrics_saved':good}

def refresh(browser=False,metrics=False):
    initialize();events,errors=fetch_all_calendars(days=90)
    official=list(events)
    for name,fetch in [('Ticketmaster',lambda:fetch_ticketmaster(90,official)),('JamBase',lambda:fetch_jambase(90))]:
        try:events.extend(fetch())
        except Exception as e:errors.append(name+' unavailable; cached catalog retained.')
    if browser:
        try:
            from concert_discovery.browser_sources import fetch_browser_calendars
            rows,failures=fetch_browser_calendars(90);events.extend(rows);errors.extend(failures)
        except Exception:errors.append('Browser calendars unavailable; cached catalog retained.')
    save_events(events)
    result={'source_records':len(events),'warnings':errors}
    if metrics:result.update(enrich())
    Path(DATABASE_PATH).with_name('freshness.json').write_text(json.dumps({'refreshed_at':utc_now(),**result},indent=2))
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser',action='store_true');parser.add_argument('--metrics',action='store_true');args=parser.parse_args()
    print(json.dumps(refresh(args.browser,args.metrics)))
