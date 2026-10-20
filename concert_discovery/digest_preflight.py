"""Small, cache-respecting retry for selected digest rows; no calendar collection."""
def prepare(shows, db_path, attempted_artists=None):
    from concert_discovery.matching_queue import run
    from concert_discovery.refresh import enrich
    from concert_discovery.discovery import get_shows
    from concert_discovery.pastspot import refresh_history
    from concert_discovery.price_refresh import refresh
    from concert_discovery.ticketmaster_prices import refresh as ticketmaster
    from concert_discovery.metadata_outcomes import synchronize
    from concert_discovery.operations_alerts import check
    from concert_discovery.digest_readiness import audit
    pending={r['show_id']:r['pending'] for r in audit(shows,db_path)}
    shows=[s for s in shows if s['show_id'] in pending]
    if not shows:return {'preflight_warnings':[],'preflight_skipped':'No unresolved metadata fetches'}
    ids={a['artist_id'] for s in shows for a in s.get('headliners',[])}
    if attempted_artists is not None:
        ids-=attempted_artists
        attempted_artists.update(ids)
    keys={s['dedupe_key'] for s in shows}
    from concert_discovery.pipeline_steps import attempt
    result={};warnings=[]
    attempt(result,warnings,'Spotify matching',lambda:run(limit=max(5,len(ids)),db_path=db_path,artist_ids=ids,discover_sources=False,force=True))
    attempt(result,warnings,'Listeners and artwork',lambda:enrich(limit=max(10,len(ids)),db_path=db_path,artist_ids=ids))
    updated=[s for s in get_shows(db_path) if s['dedupe_key'] in keys]
    spotify_ids={a['spotify_artist_id'] for s in updated for a in s['headliners'] if a['artist_id'] in ids and a.get('spotify_artist_id') and any(f=='growth: '+a['display_name'] for f in pending.get(s['show_id'],[]))}
    price_shows=[s for s in updated if any(f in ('tickets','ticket price') for f in pending.get(s['show_id'],[]))]
    attempt(result,warnings,'Growth',lambda:refresh_history(db_path,limit=max(10,len(spotify_ids)),spotify_ids=spotify_ids,force=True))
    attempt(result,warnings,'Ticket pages',lambda:refresh(db_path=db_path,limit=max(3,len(price_shows)),shows=price_shows,force=True))
    attempt(result,warnings,'Ticketmaster prices',lambda:ticketmaster(db_path=db_path,limit=max(2,len(price_shows)),shows=price_shows,force=True))
    result.update(synchronize(db_path));result.update(check(db_path))
    result['preflight_warnings']=warnings
    return result
