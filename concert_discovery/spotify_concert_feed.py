"""Optional CheckLeaked concert feed adapter. Separate provider key; never Spotify credentials."""
from datetime import date
import requests
from concert_discovery.source_links import spotify_artist_ids
from concert_discovery.event_sources import venue_id_for
from concert_discovery.api_sources import secret,event


def parse_feed(payload):
    rows={};cursor=None
    def walk(value):
        nonlocal cursor
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            if value.get('paginationKey'):cursor=value['paginationKey']
            uri=value.get('uri','')
            if uri.startswith('spotify:concert:') and value.get('startDateIsoString'):
                location=value.get('location') or {};venue=venue_id_for(location.get('name',''))
                start=value['startDateIsoString']
                if venue and start[:10]>=date.today().isoformat():
                    acts=[];links={}
                    for i,item in enumerate((value.get('artists') or {}).get('items',[])):
                        artist=item.get('data') or {};name=(artist.get('profile') or {}).get('name');ids=spotify_artist_ids(artist.get('uri',''))
                        if not name:continue
                        # Feed order alone doesn't prove every artist is a co-headliner.
                        acts.append(dict(name=name,role='headliner_candidate' if i==0 else 'support',confidence=1,note='Spotify feed lineup order; official billing preferred.'))
                        if len(ids)==1:links[name]=ids.pop()
                    if acts:
                        url='https://open.spotify.com/concert/'+uri.split(':')[-1]
                        row=event('SpotifyConcertFeed',uri,value.get('title') or acts[0]['name'],start,venue,acts,links=links)
                        row['source_url']=url;row['venue_as_reported']=location.get('name','');rows[uri]=row
            for child in value.values():
                if isinstance(child,(dict,list)):walk(child)
    walk(payload)
    return list(rows.values()),cursor


def fetch_feed(max_pages=8):
    key=secret('CHECKLEAKED_API_KEY')
    if not key:return [],'Spotify concert feed not enabled: separate CheckLeaked provider key missing.'
    rows=[];seen=set();cursor=None
    for _ in range(min(max_pages,8)):
        # Uses the same conservative shared request ledger as JamBase, in a separate file.
        from concert_discovery.api_sources import reserve_jambase
        from concert_discovery.storage import DATABASE_PATH
        reserve_jambase(DATABASE_PATH,ledger_name='checkleaked_budget.sqlite3')
        params={'geoHash':'dnm692vyxfj4','geonameId':'4453066','radiusInKm':50,'from':date.today().isoformat(),'details':'false'}
        if cursor:params['paginationKey']=cursor
        response=requests.get('https://spotify-proxy.checkleaked.cc/partner/concert-feed',params=params,headers={'x-api-key':key},timeout=25)
        response.raise_for_status();batch,next_cursor=parse_feed(response.json());rows.extend(batch)
        if not next_cursor:return rows,None
        if next_cursor in seen:return rows,'Spotify concert feed repeated a cursor; retained partial results.'
        seen.add(next_cursor);cursor=next_cursor
    return rows,'Spotify concert feed page budget reached; coverage is partial.'
