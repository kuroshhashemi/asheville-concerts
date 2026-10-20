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
        first_import=c.execute('SELECT count(*) FROM shows').fetchone()[0]==0
        for e in events:
            if not e.get('venue_id'):continue
            from concert_discovery.bill_evidence import apply
            e=apply(c,e)
            upsert_show(c,e)
            from concert_discovery.prices import save as save_price
            save_price(e,e.get('advertised_price'))
            for name,metadata in e.get('artist_metadata',{}).items():
                aid=upsert_artist(c,name)
                from concert_discovery.source_links import schema
                schema(c)
                from concert_discovery.source_links import record
                for sid in metadata.get('spotify_candidates',[]):
                    record(c,aid,sid,e['source_url'],'Provider performer metadata')
                for url in metadata.get('source_pages',[]):
                    c.execute('INSERT OR IGNORE INTO artist_source_pages VALUES(?,?)',(aid,url))
                genre=metadata.get('genre')
                if genre and genre.lower() not in ('undefined','music') and e['source_url'].startswith(('https://www.jambase.com/', 'https://jambase.com/')):
                    c.execute('INSERT INTO artist_genres(artist_id,genre,source_url) VALUES(?,?,?) ON CONFLICT(artist_id) DO UPDATE SET genre=excluded.genre,source_url=excluded.source_url',(aid,genre,e['source_url']))

    if first_import:
        with connect(db_path) as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='show_discovery'").fetchone():c.execute('UPDATE show_discovery SET eligible=0')
    from concert_discovery.artist_identity import reconcile
    reconcile(db_path)
    from concert_discovery.matching_queue import enqueue
    enqueue(db_path)

def enrich(limit=40,db_path=DATABASE_PATH,artist_ids=None,priority_ids=None):
    with connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS identity_attempts(artist_id TEXT PRIMARY KEY,checked_at TEXT)')
        artists=[dict(r) for r in c.execute("""SELECT DISTINCT a.* FROM artists a JOIN show_artists sa USING(artist_id) JOIN shows s USING(show_id)
            WHERE sa.billing_role LIKE '%headliner%' AND substr(s.performance_start,1,10)>=date('now')
            ORDER BY a.spotify_artist_id IS NULL,s.performance_start""")]
    if artist_ids is not None:artists=[a for a in artists if a["artist_id"] in artist_ids]
    with connect(db_path) as c:
        attempts={r[0]:r[1] for r in c.execute('SELECT artist_id,MAX(retrieved_at) FROM artist_metric_snapshots GROUP BY artist_id')}
    artists.sort(key=lambda a:(a['artist_id'] not in (priority_ids or set()),attempts.get(a['artist_id'],'')))
    from concert_discovery.spotify_matching import SpotifySearch,SpotifyUnavailable,match_artist,match_bandsintown_link
    try:search=SpotifySearch()
    except (SpotifyUnavailable,requests.RequestException) as error:search=None;artwork_error=type(error).__name__
    else:artwork_error=None
    attempted=0;good=0
    for a in artists:
        # Unresolved identities are exclusively handled by the durable queue.
        if not a['spotify_artist_id']:continue
        if attempted>=limit:break
        with connect(db_path) as c:
            fresh=c.execute("SELECT 1 FROM artist_metric_snapshots WHERE artist_id=? AND status='success' AND source_url=? AND retrieved_at>=?",(a['artist_id'],a['spotify_profile_url'],(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())).fetchone()
            recent=c.execute("SELECT 1 FROM identity_attempts WHERE artist_id=? AND checked_at>=?",(a['artist_id'],(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())).fetchone()
        image_present=c.execute('SELECT 1 FROM artist_images WHERE artist_id=? AND source_url=?',(a['artist_id'],a['spotify_profile_url'])).fetchone()
        if (fresh and image_present) or (not a['spotify_artist_id'] and recent):continue
        attempted+=1
        if not image_present:
            art_status='blocked';art_detail=artwork_error or 'Spotify artwork request unavailable'
            if search:
                try:
                    found=search.artwork(a,db_path);art_status='complete' if found else 'unresolved';art_detail='Verified artwork saved' if found else 'No verified image returned'
                except (SpotifyUnavailable,requests.RequestException,ValueError,TypeError) as error:
                    art_detail=type(error).__name__;search=None;artwork_error=art_detail
            with connect(db_path) as c:
                c.execute('CREATE TABLE IF NOT EXISTS artwork_checks(artist_id TEXT PRIMARY KEY,checked_at TEXT,status TEXT,detail TEXT)')
                c.execute('INSERT OR REPLACE INTO artwork_checks VALUES(?,?,?,?)',(a['artist_id'],utc_now(),art_status,art_detail))
        if not a['spotify_artist_id']:
            with connect(db_path) as c:c.execute('INSERT OR REPLACE INTO identity_attempts VALUES(?,?)',(a['artist_id'],utc_now()))
            from concert_discovery.source_links import apply_candidates
            try:
                verified=apply_candidates(a,db_path) or match_bandsintown_link(a,db_path)
                if verified:
                    result=collect_artist_metric(a['artist_id'],db_path,verified_metrics=verified)
                    good+=result['status']=='success'
                    continue
            except SpotifyUnavailable:break
            except (requests.RequestException,ValueError,TypeError,PermissionError,RuntimeError):pass
            if search:
                try:
                    match_artist(search,a,db_path)
                    with connect(db_path) as c:
                        linked=c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(a['artist_id'],)).fetchone()[0]
                    if linked:
                        result=collect_artist_metric(a['artist_id'],db_path)
                        good+=result['status']=='success'
                        if result['status'] in ('blocked','rate_limited'):break
                        continue
                except SpotifyUnavailable:break
                except (requests.RequestException,ValueError,TypeError):pass
            try:
                verified=match_bandsintown_link(a,db_path)
                if not verified:continue
                result=collect_artist_metric(a['artist_id'],db_path,verified_metrics=verified)
                good+=result['status']=='success'
                continue
            except SpotifyUnavailable:break
            except (requests.RequestException,ValueError,TypeError,PermissionError,RuntimeError):continue
        result=collect_artist_metric(a['artist_id'],db_path)
        good+=result['status']=='success'
        if result['status'] in ('blocked','rate_limited'):break
    return {'attempted':attempted,'metrics_saved':good}

def refresh(browser=False,metrics=False,db_path=None):
    db_path=Path(db_path or DATABASE_PATH)
    initialize(db_path);snapshots=[];events,errors=fetch_all_calendars(snapshots=snapshots)
    official=list(events)
    for name,fetch in [('Ticketmaster',lambda:fetch_ticketmaster(None,official)),('JamBase',lambda:fetch_jambase(db_path=db_path))]:
        try:events.extend(fetch())
        except Exception as e:errors.append(name+' unavailable; cached catalog retained.')
    if browser:
        try:
            from concert_discovery.browser_sources import fetch_browser_calendars
            rows,failures=fetch_browser_calendars(snapshots=snapshots);events.extend(rows);errors.extend(failures)
        except Exception:errors.append('Browser calendars unavailable; cached catalog retained.')
    from concert_discovery.spotify_concert_feed import fetch_feed
    try:
        feed_rows,warning=fetch_feed();events.extend(feed_rows)
        if warning:errors.append(warning)
    except requests.RequestException:errors.append('Spotify concert feed connection failed; cached catalog retained.')
    except RuntimeError:errors.append('Spotify concert feed request budget reached; cached catalog retained.')
    from concert_discovery.collection_health import CORE
    return apply_refresh(events,snapshots,errors,metrics=metrics,db_path=db_path,expected_venues=set(CORE),browser_prices=browser)

def apply_refresh(events,snapshots,errors=(),metrics=False,db_path=DATABASE_PATH,matching_limit=25,expected_venues=None,browser_prices=False):
    """The same bounded follow-through runs for every refresh, including staged audits."""
    from concert_discovery.collection_health import start,observation,finish
    from concert_discovery.calendar_presence import record_snapshot
    from concert_discovery.dedupe import cleanup_duplicates
    from concert_discovery.discovery import get_shows
    before={s['dedupe_key'] for s in get_shows(db_path)}
    errors=list(errors);rid=start(db_path)
    try:
        from concert_discovery.bill_evidence import enrich_events
        enrich_events(events,db_path)
        save_events(events,db_path)
        from concert_discovery.sierra_calendar import reconcile_urls
        reconcile_urls(events,db_path)
        merges=cleanup_duplicates(db_path)
        # HTTP and browser copies are one venue check per refresh, not two absences.
        checked=set()
        for snapshot in snapshots:
            vid=snapshot['venue_id']
            if vid in checked:continue
            checked.add(vid)
            if observation(rid,snapshot,db_path):
                record_snapshot(dict(snapshot,check_id=rid+':'+vid),db_path)
            else:errors.append(vid+': suspicious calendar drop; prior listings retained')
    except Exception as error:
        finish(rid,errors+[type(error).__name__+': '+str(error)],db_path)
        raise
    from concert_discovery.collection_health import missing_checks
    missing_checks(rid,checked,errors,db_path,expected_venues=expected_venues)
    result={'source_records':len(events),'warnings':errors,'duplicates_consolidated':merges,'run_id':rid}
    visible=get_shows(db_path)
    from concert_discovery.show_validation import partition
    _,conflicted=partition(visible,visible,db_path)
    result['show_validation_issues']=conflicted
    new_keys={s['dedupe_key'] for s in visible}-before
    new_shows=[s for s in visible if s['dedupe_key'] in new_keys]
    new_artist_ids={a['artist_id'] for s in new_shows for a in s['headliners']}
    result['new_shows_for_enrichment']=len(new_shows)
    from concert_discovery.metadata_outcomes import synchronize
    synchronize(db_path)
    from concert_discovery.matching_queue import run
    from concert_discovery.pipeline_steps import attempt
    attempt(result,errors,'Spotify matching',lambda:run(limit=max(matching_limit,len(new_artist_ids)),db_path=db_path,priority_ids=new_artist_ids))
    if metrics:
        from concert_discovery.source_links import discover
        attempt(result,errors,'Source links',lambda:discover(db_path))
        attempt(result,errors,'Listeners and artwork',lambda:enrich(limit=max(40,len(new_artist_ids)),db_path=db_path,priority_ids=new_artist_ids))
        from concert_discovery.pastspot import refresh_history
        updated=get_shows(db_path)
        priority_spotify={a['spotify_artist_id'] for s in updated if s['dedupe_key'] in new_keys for a in s['headliners'] if a.get('spotify_artist_id')}
        attempt(result,errors,'Growth',lambda:refresh_history(db_path,limit=max(40,len(priority_spotify)),priority_ids=priority_spotify))
    from concert_discovery.price_refresh import refresh as refresh_prices
    try:result.update(refresh_prices(db_path=db_path,limit=max(12,len(new_shows)),priority_ids={s["show_id"] for s in new_shows}))
    except Exception as error:
        errors.append('Price checks unavailable; saved prices retained ('+type(error).__name__+')')
    from concert_discovery.ticketmaster_prices import refresh as ticketmaster_prices
    try:result.update(ticketmaster_prices(db_path=db_path,limit=max(12,len(new_shows)),priority_ids={s["show_id"] for s in new_shows}))
    except Exception as error:errors.append('Ticketmaster prices unavailable; saved prices retained ('+type(error).__name__+')')
    from concert_discovery.brightdata_prices import refresh as bright_prices
    try:result.update(bright_prices(db_path=db_path,priority_ids={s["show_id"] for s in new_shows}))
    except Exception as error:errors.append('Bright Data prices unavailable; saved prices retained ('+type(error).__name__+')')
    if browser_prices:
        from concert_discovery.browser_prices import refresh as render_prices
        try:result.update(render_prices(db_path=db_path,priority_ids={s["show_id"] for s in new_shows}))
        except Exception as error:errors.append('Rendered prices unavailable; saved prices retained ('+type(error).__name__+')')
    try:
        result.update(synchronize(db_path))
        from concert_discovery.operations_alerts import check as check_operations
        result.update(check_operations(db_path))
    except Exception as error:errors.append('Metadata health unavailable ('+type(error).__name__+')')
    finish(rid,errors,db_path)
    Path(db_path).with_name('freshness.json').write_text(json.dumps({'refreshed_at':utc_now(),'pipeline_completed':True,'enrichment_completed':bool(metrics),'collection_usable':bool(events or checked),**result},indent=2))
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser',action='store_true');parser.add_argument('--metrics',action='store_true');args=parser.parse_args()
    print(json.dumps(refresh(args.browser,args.metrics)))
