"""Durable, bounded identity work following every catalog import."""
from datetime import datetime, timezone, timedelta
import requests
from concert_discovery.storage import connect, utc_now, DATABASE_PATH


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS artist_matching_jobs(
        artist_id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT,
        next_attempt_at TEXT, detail TEXT, metric_status TEXT)''')


def enqueue(db_path=DATABASE_PATH):
    from concert_discovery.discovery import get_shows
    artists={a['artist_id']:a for show in get_shows(db_path) for a in show['headliners'] if a.get('entity_kind','artist')=='artist'}
    with connect(db_path) as c:
        schema(c)
        for aid,a in artists.items():
            if a.get('spotify_artist_id'):
                c.execute('''INSERT INTO artist_matching_jobs(artist_id,name,state,detail)
                  VALUES(?,?,'matched','Existing identity retained') ON CONFLICT(artist_id)
                  DO UPDATE SET name=excluded.name,state='matched',next_attempt_at=NULL''',(aid,a['display_name']))
            else:
                c.execute('''INSERT INTO artist_matching_jobs(artist_id,name,state,next_attempt_at)
                  VALUES(?,?,'pending',?) ON CONFLICT(artist_id) DO UPDATE SET
                  state=CASE WHEN name!=excluded.name OR state='matched' THEN 'pending' ELSE state END,
                  next_attempt_at=CASE WHEN name!=excluded.name OR state='matched' THEN excluded.next_attempt_at ELSE next_attempt_at END,
                  name=excluded.name''',(aid,a['display_name'],utc_now()))
    return set(artists)


def run(limit=25,db_path=DATABASE_PATH,artist_ids=None,discover_sources=True):
    from concert_discovery.spotify_matching import SpotifySearch, SpotifyUnavailable, match_artist, match_bandsintown_link
    from concert_discovery.source_links import apply_candidates, discover
    from concert_discovery.collector import collect_artist_metric
    visible=enqueue(db_path)
    with connect(db_path) as c:
        jobs=[dict(r) for r in c.execute("SELECT a.* FROM artist_matching_jobs j JOIN artists a USING(artist_id) WHERE j.state!='matched' AND (j.next_attempt_at IS NULL OR j.next_attempt_at<=?) ORDER BY j.last_attempt_at IS NOT NULL,j.last_attempt_at,j.artist_id",(utc_now(),)) if r['artist_id'] in visible and (artist_ids is None or r['artist_id'] in artist_ids)][:limit]
    result={'matching_attempted':0,'matching_matched':0,'matching_ambiguous':0,'matching_blocked':0,'matching_pending':0}
    if not jobs:return result
    source_error=None
    if discover_sources:
        try:result.update(discover(db_path,budget=40,artist_ids={a['artist_id'] for a in jobs}))
        except (requests.RequestException,RuntimeError,ValueError) as e:source_error=type(e).__name__
    search=None
    try:search=SpotifySearch()
    except (SpotifyUnavailable,requests.RequestException) as e:auth_error=str(e)
    else:auth_error=None
    for artist in jobs:
        artist_source_error=source_error
        state='ambiguous';detail='No unique exact candidate or verified source link';metric=None;verified=None
        try:
            verified=apply_candidates(artist,db_path)
            if not verified:
                try:verified=match_bandsintown_link(artist,db_path)
                except (requests.RequestException,ValueError,RuntimeError) as e:
                    artist_source_error=type(e).__name__
            if not verified and search:
                detail=match_artist(search,artist,db_path)
            elif not verified and not search:
                raise SpotifyUnavailable(auth_error or 'Spotify search unavailable')
            canonical_aid=(verified or {}).get('canonical_artist_id',artist['artist_id'])
            with connect(db_path) as c:
                linked=c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(canonical_aid,)).fetchone()[0]
            if linked:
                state='matched';detail='Source-verified identity' if verified else 'Unique exact Spotify candidate'
                try:metric=collect_artist_metric(canonical_aid,db_path,verified_metrics=verified)['status']
                except (requests.RequestException,RuntimeError,ValueError) as e:metric='collection_error: '+type(e).__name__
            elif artist_source_error:
                state='blocked';detail+='; source lookup incomplete: '+artist_source_error
        except (SpotifyUnavailable,requests.RequestException,RuntimeError,ValueError,TypeError) as e:
            state='blocked';detail=type(e).__name__+': '+str(e)[:160]
        retry=None if state=='matched' else (datetime.now(timezone.utc)+timedelta(days=1 if state=='blocked' else 7)).isoformat()
        with connect(db_path) as c:
            c.execute('''UPDATE artist_matching_jobs SET state=?, attempts=attempts+1,
              last_attempt_at=?,next_attempt_at=?,detail=?,metric_status=? WHERE artist_id=?''',
              (state,utc_now(),retry,detail,metric,artist['artist_id']))
        result['matching_attempted']+=1;result['matching_'+state]+=1
    with connect(db_path) as c:
        result['matching_pending']=sum(r['artist_id'] in visible for r in c.execute("SELECT artist_id FROM artist_matching_jobs WHERE state='pending'"))
    return result
