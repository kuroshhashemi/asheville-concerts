"""Small, cache-respecting retry for selected digest rows; no calendar collection."""
def prepare(shows, db_path):
    from concert_discovery.matching_queue import run
    from concert_discovery.refresh import enrich
    from concert_discovery.discovery import get_shows
    from concert_discovery.pastspot import refresh_history
    from concert_discovery.price_refresh import refresh
    from concert_discovery.ticketmaster_prices import refresh as ticketmaster
    from concert_discovery.metadata_outcomes import synchronize
    from concert_discovery.operations_alerts import check
    ids={a['artist_id'] for s in shows for a in s.get('headliners',[])}
    keys={s['dedupe_key'] for s in shows}
    result=run(limit=5,db_path=db_path,artist_ids=ids,discover_sources=False)
    result.update(enrich(limit=10,db_path=db_path,artist_ids=ids))
    updated=[s for s in get_shows(db_path) if s['dedupe_key'] in keys]
    spotify_ids={a['spotify_artist_id'] for s in updated for a in s['headliners'] if a.get('spotify_artist_id')}
    result.update(refresh_history(db_path,limit=10,spotify_ids=spotify_ids))
    result.update(refresh(db_path=db_path,limit=3,shows=updated))
    result.update(ticketmaster(db_path=db_path,limit=2,shows=updated))
    result.update(synchronize(db_path));result.update(check(db_path))
    return result
