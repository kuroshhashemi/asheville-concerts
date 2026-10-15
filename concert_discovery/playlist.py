"""One shared playlist: cached public Popular tracks, owner-authorized playlist edits."""
import argparse
import json
import re
from pathlib import Path
from datetime import datetime,timezone,timedelta,date
import requests
from concert_discovery.api_sources import secret
from concert_discovery.spotify_public import fetch_public_artist_profile
from concert_discovery.storage import DATABASE_PATH,connect
from concert_discovery.discovery import get_shows
from concert_discovery.event_classification import category_for

PLAYLIST_ID='7u3M8wAdhF71129WF72miQ'
CACHE=Path(__file__).parent/'assets/playlist-tracks.json'


def select_artists(shows, categories, size=75):
    """80% audience leaders; 20% positive growth from the next audience-sized band."""
    artists={}
    for show in shows:
        if categories.get(show['show_id'])!='live_music':continue
        if str(show['performance_start'])[:10]<date.today().isoformat():continue
        for artist in show['headliners']:
            sid=artist.get('spotify_artist_id')
            if not sid or not re.fullmatch(r'[A-Za-z0-9]{22}',sid):continue
            if artist.get('entity_kind','artist')!='artist':continue
            count=artist.get('monthly_listeners')
            if count is None:continue
            existing=artists.get(sid)
            if existing is None or count>(existing.get('monthly_listeners') or 0):artists[sid]=artist
    ranked=sorted(artists.values(),key=lambda a:(-a['monthly_listeners'],a['spotify_artist_id']))
    popular_count=round(size*.8)
    popular=ranked[:popular_count]
    rising=sorted((a for a in ranked[popular_count:popular_count+size] if (a.get('listener_growth_6m') or 0)>0),
                  key=lambda a:(-a['listener_growth_6m'],-a['monthly_listeners'],a['spotify_artist_id']))[:size-popular_count]
    chosen=popular+rising
    ids={a['spotify_artist_id'] for a in chosen}
    chosen+= [a for a in ranked if a['spotify_artist_id'] not in ids][:max(0,size-len(chosen))]
    return chosen[:size]


def collect_tracks(artists, cache, fetch=fetch_public_artist_profile, now=None):
    now=now or datetime.now(timezone.utc)
    tracks=[]
    for artist in artists:
        sid=artist['spotify_artist_id'];entry=cache.get(sid)
        fresh=False
        try:fresh=datetime.fromisoformat(entry['checked_at'])>now-timedelta(days=7)
        except (TypeError,KeyError,ValueError):pass
        if not fresh:
            profile=fetch(sid)
            track=profile.get('top_track')
            if not track or track.get('artist_id')!=sid:raise RuntimeError('Popular track unavailable; playlist retained.')
            entry={'checked_at':now.isoformat(),'track':track};cache[sid]=entry
        if entry['track'].get('artist_id')!=sid:raise RuntimeError('Cached track identity mismatch; playlist retained.')
        uri=entry['track']['uri']
        if not re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}',uri):raise RuntimeError('Invalid track; playlist retained.')
        if uri not in tracks:tracks.append(uri)
    return tracks


def access_token():
    required={k:secret(k) for k in ('SPOTIFY_CLIENT_ID','SPOTIFY_CLIENT_SECRET','SPOTIFY_REFRESH_TOKEN')}
    if not all(required.values()):raise RuntimeError('One-time playlist-owner authorization is required.')
    r=requests.post('https://accounts.spotify.com/api/token',auth=(required['SPOTIFY_CLIENT_ID'],required['SPOTIFY_CLIENT_SECRET']),
                    data={'grant_type':'refresh_token','refresh_token':required['SPOTIFY_REFRESH_TOKEN']},timeout=20)
    if r.status_code!=200:raise RuntimeError('Spotify authorization failed (HTTP %s).'%r.status_code)
    return r.json()['access_token']


def publish(tracks,token,session=requests):
    if not 50<=len(tracks)<=100 or len(set(tracks))!=len(tracks) or any(not re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}',uri) for uri in tracks):raise RuntimeError('Expected 50–100 distinct tracks; existing playlist retained.')
    headers={'Authorization':'Bearer '+token}
    me=session.get('https://api.spotify.com/v1/me',headers=headers,timeout=20)
    info=session.get('https://api.spotify.com/v1/playlists/'+PLAYLIST_ID,headers=headers,timeout=20)
    if me.status_code!=200 or info.status_code!=200:raise RuntimeError('Could not verify playlist ownership.')
    if info.json().get('owner',{}).get('id')!=me.json().get('id'):raise RuntimeError('Please authorize the playlist owner.')
    current=session.get('https://api.spotify.com/v1/playlists/'+PLAYLIST_ID+'/items',headers=headers,params={'limit':100},timeout=20)
    if current.status_code!=200:raise RuntimeError('Could not read existing playlist; no changes made.')
    data=current.json();items=data.get('items')
    if items is None:raise RuntimeError('Playlist items unavailable; no changes made.')
    uris=[(i.get('item') or i.get('track') or {}).get('uri') for i in items]
    if not data.get('next') and uris==tracks:return 'unchanged'
    r=session.put('https://api.spotify.com/v1/playlists/'+PLAYLIST_ID+'/items',headers=headers,json={'uris':tracks},timeout=20)
    if r.status_code not in (200,201):raise RuntimeError('Spotify update failed (HTTP %s); no automatic retry.'%r.status_code)
    return 'updated'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    shows=get_shows(user_id='playlist')
    with connect() as c:categories={s['show_id']:category_for(c,s['show_id'],s['title'])['category'] for s in shows}
    artists=select_artists(shows,categories)
    token=access_token() if args.publish else None
    cache=json.loads(CACHE.read_text()) if CACHE.exists() else {}
    try:tracks=collect_tracks(artists,cache)
    finally:
        tmp=CACHE.with_suffix('.tmp');tmp.write_text(json.dumps(cache));tmp.replace(CACHE)
    result=publish(tracks,token) if args.publish else 'preview'
    print(json.dumps({'result':result,'artists':len(artists),'tracks':len(tracks)}))

if __name__=='__main__':main()
