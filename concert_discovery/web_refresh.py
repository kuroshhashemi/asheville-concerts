"""One-source refresh for the parallel web app, using existing Python collectors."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from concert_discovery.storage import DATABASE_PATH,initialize,connect,utc_now
from concert_discovery.official_calendar import fetch_all_calendars
from concert_discovery.refresh import save_events,enrich
from concert_discovery.discovery import get_shows
from concert_discovery.collection_health import start,observation,finish
from concert_discovery.calendar_presence import record_snapshot
from concert_discovery.dedupe import cleanup_duplicates
from concert_discovery.web_snapshot import export
SOURCES=('HarrahOfficial','OrangePeelOfficial','MusicHallOfficial','GreyEagleOfficial','EulogyOfficial','BrevardOfficial','SierraOfficial')

def run(source,db_path=DATABASE_PATH):
    initialize(db_path);snapshots=[];rid=start(db_path);errors=[]
    try:
        if source=='SierraOfficial':
            from concert_discovery.sierra_calendar import fetch_api
            events=fetch_api(snapshots=snapshots)
        else:events,errors=fetch_all_calendars(snapshots=snapshots,sources={source})
        if errors or not snapshots:raise RuntimeError('Calendar did not return a complete snapshot')
        save_events(events,db_path);cleanup_duplicates(db_path)
        for snapshot in snapshots:
            if observation(rid,snapshot,db_path):record_snapshot(dict(snapshot,check_id=rid+':'+snapshot['venue_id']),db_path)
            else:errors.append('Calendar drop needs review; prior listings retained')
        vids={s['venue_id'] for s in snapshots};shows=[s for s in get_shows(db_path) if s['venue_id'] in vids]
        aids={a['artist_id'] for s in shows for a in s['headliners']};sids={a['spotify_artist_id'] for s in shows for a in s['headliners'] if a.get('spotify_artist_id')}
        from concert_discovery.matching_queue import run as match
        from concert_discovery.source_links import discover
        match(limit=len(aids),db_path=db_path,artist_ids=aids)
        # Each optional field is isolated: one provider cannot cancel other fields.
        from concert_discovery.pastspot import refresh_history
        from concert_discovery.price_refresh import refresh as prices
        from concert_discovery.ticketmaster_prices import refresh as tm
        from concert_discovery.brightdata_prices import refresh as bright
        for name,call in [('source links',lambda:discover(db_path,artist_ids=aids)),('listeners',lambda:enrich(limit=len(aids),db_path=db_path,artist_ids=aids)),('growth',lambda:refresh_history(db_path,limit=len(sids),spotify_ids=sids)),('prices',lambda:prices(db_path=db_path,shows=shows)),('Ticketmaster prices',lambda:tm(db_path=db_path,shows=shows)),('provider prices',lambda:bright(db_path=db_path,shows=shows))]:
            try:call()
            except Exception:errors.append(name+' unavailable; saved data retained')
        from concert_discovery.metadata_outcomes import synchronize
        synchronize(db_path);finish(rid,errors,db_path)
        path=Path(db_path).with_name('freshness.json');state=json.loads(path.read_text()) if path.exists() else {}
        state['web_updated_at']=utc_now();path.write_text(json.dumps(state))
        return {'events':len(events),'warnings':errors}
    except Exception:
        finish(rid,errors+['Targeted source refresh failed; saved data retained'],db_path);raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',choices=SOURCES,required=True);a=p.parse_args();print(json.dumps(run(a.source)))
