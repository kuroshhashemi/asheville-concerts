"""Bounded official artist search. Name matches remain candidates, not confirmations."""
import re, unicodedata
import requests
from concert_discovery.api_sources import secret
from concert_discovery.storage import connect,utc_now,upsert_artist

class SpotifyUnavailable(RuntimeError):
    pass

def name_key(value):
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().casefold())

def select_candidate(name,items):
    if not name_key(name):return None
    exact={a['id']:a for a in items if a.get('id') and name_key(a.get('name',''))==name_key(name)}
    return next(iter(exact.values())) if len(exact)==1 else None

class SpotifySearch:
    def __init__(self):
        key=secret('SPOTIFY_CLIENT_ID');password=secret('SPOTIFY_CLIENT_SECRET')
        if not key or not password:raise SpotifyUnavailable('Spotify credentials unavailable.')
        r=requests.post('https://accounts.spotify.com/api/token',auth=(key,password),data={'grant_type':'client_credentials'},timeout=20)
        if r.status_code!=200:raise SpotifyUnavailable('Spotify authentication unavailable (HTTP %s).'%r.status_code)
        self.session=requests.Session();self.session.headers['Authorization']='Bearer '+r.json()['access_token']
    def artwork(self,artist,db_path):
        sid=artist['spotify_artist_id']
        r=self.session.get('https://api.spotify.com/v1/artists/'+sid,timeout=20)
        if r.status_code in (401,403,429):raise SpotifyUnavailable('Spotify artwork lookup paused (HTTP %s).'%r.status_code)
        r.raise_for_status();data=r.json()
        if name_key(data.get('name',''))!=name_key(artist['display_name']) or not data.get('images'):return False
        with connect(db_path) as c:
            c.execute('INSERT OR REPLACE INTO artist_images VALUES(?,?,?,?)',(artist['artist_id'],data['images'][-1]['url'],'https://open.spotify.com/artist/'+sid,utc_now()))
        return True
    def search(self,name):
        r=self.session.get('https://api.spotify.com/v1/search',params={'q':'artist:"'+name+'"','type':'artist','limit':10},timeout=20)
        if r.status_code in (401,403,429):raise SpotifyUnavailable('Spotify search stopped (HTTP %s); cached data retained.'%r.status_code)
        r.raise_for_status()
        items=r.json().get('artists',{}).get('items',[])
        if not any(name_key(a.get('name',''))==name_key(name) for a in items):
            # Spotify's field-filtered search can miss apostrophes and stage names.
            query=name.replace('’', "'").replace('"','')
            r=self.session.get('https://api.spotify.com/v1/search',params={'q':query,'type':'artist','limit':10},timeout=20)
            if r.status_code in (401,403,429):raise SpotifyUnavailable('Spotify search stopped (HTTP %s).'%r.status_code)
            r.raise_for_status();items=r.json().get('artists',{}).get('items',[])
        return items

def match_artist(client,artist,db_path):
    items=client.search(artist['display_name']);chosen=select_candidate(artist['display_name'],items)
    with connect(db_path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS spotify_match_candidates(
          artist_id TEXT,spotify_id TEXT,name TEXT,profile_url TEXT,checked_at TEXT,
          PRIMARY KEY(artist_id,spotify_id))''')
        c.execute('DELETE FROM spotify_match_candidates WHERE artist_id=?',(artist['artist_id'],))
        for a in items:
            c.execute('INSERT INTO spotify_match_candidates VALUES(?,?,?,?,?)',(artist['artist_id'],a['id'],a['name'],'https://open.spotify.com/artist/'+a['id'],utc_now()))
        if not chosen:return 'ambiguous_or_no_exact_match'
        sid=chosen['id'];profile='https://open.spotify.com/artist/'+sid
        upsert_artist(c,artist['display_name'],sid,'Unique exact normalized name in official Spotify search; candidate identity, not independently confirmed.')
        actual=c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(artist['artist_id'],)).fetchone()[0]
        if actual!=sid:return 'identity_conflict'
        c.execute("UPDATE artists SET match_status='candidate',match_confidence=NULL WHERE artist_id=?",(artist['artist_id'],))
        if chosen.get('images'):
            c.execute('INSERT OR REPLACE INTO artist_images VALUES(?,?,?,?)',(artist['artist_id'],chosen['images'][-1]['url'],profile,utc_now()))
        if chosen.get('genres'):
            c.execute('INSERT OR REPLACE INTO artist_genres VALUES(?,?,?)',(artist['artist_id'],', '.join(chosen['genres']),profile))
    return 'candidate'

def match_bandsintown_link(artist,db_path):
    """Use an explicit source link; retain candidate status for same-name ambiguity."""
    from urllib.parse import quote
    from concert_discovery.spotify_public import fetch_public_artist_profile
    response=requests.get('https://rest.bandsintown.com/artists/'+quote(artist['display_name'],safe=''),params={'app_id':'js_127.0.0.1'},timeout=15)
    if response.status_code in (403,429):raise SpotifyUnavailable('Bandsintown source lookup paused (HTTP %s).'%response.status_code)
    response.raise_for_status();data=response.json()
    if not isinstance(data,dict) or name_key(data.get('name',''))!=name_key(artist['display_name']):return None
    ids={m[1] for link in (data.get('links') or []) if (m:=re.search(r'open.spotify.com/artist/([A-Za-z0-9]{22})',link.get('url','')))}
    if len(ids)!=1:return None
    sid=ids.pop();profile=fetch_public_artist_profile(sid)
    expected=name_key(artist['display_name']);actual=name_key(profile['name'])
    # Exact source artist + explicit Spotify link supports a lead-artist/band-name alias.
    alias=artist['display_name'].casefold().startswith(profile['name'].casefold()+' & ')
    if expected!=actual and not alias:return None
    evidence=data.get('url') or 'https://www.bandsintown.com/'
    return remember_source_identity(artist,profile,evidence,'Explicit matching Bandsintown artist-to-Spotify link',db_path)


def remember_source_identity(artist,profile,evidence_url,method,db_path):
    """Persist canonical Spotify name and provenance; aliases are data, not code exceptions."""
    sid=profile['spotify_artist_id']
    with connect(db_path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS spotify_identity_evidence(
          artist_id TEXT PRIMARY KEY,spotify_id TEXT,profile_name TEXT,source_url TEXT,method TEXT,checked_at TEXT)''')
        upsert_artist(c,artist['display_name'],sid,method+'; evidence: '+evidence_url+'; Spotify name: '+profile['name'])
        if c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(artist['artist_id'],)).fetchone()[0]!=sid:
            raise ValueError('Spotify profile already belongs to another saved artist identity.')
        c.execute("UPDATE artists SET match_status='source_link',match_confidence=NULL WHERE artist_id=?",(artist['artist_id'],))
        c.execute('INSERT OR REPLACE INTO spotify_identity_evidence VALUES(?,?,?,?,?,?)',(artist['artist_id'],sid,profile['name'],evidence_url,method,utc_now()))
        if profile.get('image_url'):c.execute('INSERT OR REPLACE INTO artist_images VALUES(?,?,?,?)',(artist['artist_id'],profile['image_url'],profile['source_url'],utc_now()))
    return profile

def match_official_website(client,artist,url,db_path):
    """A vetted artist website's Spotify links resolve duplicates and acronyms."""
    from html import unescape
    from concert_discovery.spotify_public import fetch_public_artist_profile
    r=requests.get(url,timeout=20);r.raise_for_status();markup=unescape(r.text)
    artist_ids=set(re.findall(r'open\.spotify\.com/(?:intl-[a-z]+/)?(?:embed/)?artist/([A-Za-z0-9]{22})',markup))
    if not artist_ids:
        album_ids=set(re.findall(r'open\.spotify\.com/(?:intl-[a-z]+/)?(?:embed/)?album/([A-Za-z0-9]{22})',markup))
        for album in list(album_ids)[:3]:
            response=client.session.get('https://api.spotify.com/v1/albums/'+album,timeout=15)
            if response.status_code in (401,403,429):raise SpotifyUnavailable('Spotify album lookup paused.')
            response.raise_for_status()
            # Do not infer an identity from a compilation/collaboration album.
            performers=response.json().get('artists',[])
            if len(performers)==1:artist_ids.add(performers[0]['id'])
    if len(artist_ids)!=1:return None
    profile=fetch_public_artist_profile(artist_ids.pop())
    return remember_source_identity(artist,profile,url,'Spotify profile/album linked from vetted artist website',db_path)
