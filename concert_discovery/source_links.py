"""Source-first identity discovery, with provenance and bounded cached page reads."""
import json,re
from html import unescape
from urllib.parse import urljoin,urlparse,unquote
import requests
from concert_discovery.storage import connect,utc_now


def spotify_artist_ids(value):
    text=unquote(unescape(str(value))).replace('\\/','/')
    return set(re.findall(r'(?:open\.spotify\.com/(?:intl-[a-z]+/)?(?:embed/)?artist/|spotify:artist:)([A-Za-z0-9]{22})(?![A-Za-z0-9])',text))


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS spotify_source_candidates(
      artist_id TEXT,spotify_id TEXT,source_url TEXT,method TEXT,checked_at TEXT,
      PRIMARY KEY(artist_id,spotify_id,source_url))''')
    c.execute('''CREATE TABLE IF NOT EXISTS artist_source_pages(
      artist_id TEXT,url TEXT,PRIMARY KEY(artist_id,url))''')
    c.execute('''CREATE TABLE IF NOT EXISTS identity_page_cache(
      url TEXT PRIMARY KEY,markup TEXT,status INTEGER,checked_at TEXT)''')


def record(c,aid,sid,url,method):
    schema(c)
    c.execute('INSERT OR REPLACE INTO spotify_source_candidates VALUES(?,?,?,?,?)',(aid,sid,url,method,utc_now()))


def page_candidates(markup,names,base_url,artist_page=False):
    """Use artist-scoped JSON-LD or labeled links; never spread a bill's links to every act."""
    from concert_discovery.official_calendar import Tree
    from concert_discovery.spotify_matching import name_key
    tree=Tree();tree.feed(markup);result={name:set() for name in names};pages={name:set() for name in names}
    def add_objects(obj):
        if isinstance(obj,list):
            for item in obj:add_objects(item)
        elif isinstance(obj,dict):
            types=obj.get('@type',[]);types=[types] if isinstance(types,str) else types
            if any(t in ('MusicGroup','Person','PerformingGroup') for t in types):
                for name in names:
                    if name_key(obj.get('name',''))==name_key(name):
                        result[name].update(spotify_artist_ids(json.dumps(obj)))
                        for key in ('url','sameAs'):
                            vals=obj.get(key,[]);vals=[vals] if isinstance(vals,str) else vals
                            for url in vals:
                                if isinstance(url,str) and url.startswith('https://') and not spotify_artist_ids(url):pages[name].add(url)
            for val in obj.values():
                if isinstance(val,(dict,list)):add_objects(val)
    for node in tree.root.walk():
        if node.tag=='script' and node.attrs.get('type')=='application/ld+json':
            try:add_objects(json.loads(node.text()))
            except (ValueError,TypeError):pass
        if node.tag!='a':continue
        href=urljoin(base_url,node.attrs.get('href',''));label=node.text()
        for name in names:
            if name_key(label)==name_key(name):
                result[name].update(spotify_artist_ids(href))
                host=urlparse(href).hostname or ''
                if href!=base_url and not re.search(r'/(?:event|events|concerts)/',urlparse(href).path) and not spotify_artist_ids(href) and (re.search(r'/(?:a|artists?|bands?)/',urlparse(href).path) or host==urlparse(base_url).hostname):pages[name].add(href)
    if artist_page and len(names)==1:
        result[names[0]].update(spotify_artist_ids(markup))
    return result,pages


class PageReader:
    def __init__(self,db_path,budget=40):self.db_path=db_path;self.remaining=budget
    def get(self,url):
        parsed=urlparse(url)
        # Only externally sourced HTTPS pages; never crawl local services or send API credentials.
        if parsed.scheme!='https' or not parsed.hostname or parsed.hostname in ('localhost','127.0.0.1') or parsed.hostname.replace('.','').isdigit():return None
        with connect(self.db_path) as c:
            schema(c);row=c.execute("SELECT markup,status FROM identity_page_cache WHERE url=? AND checked_at>=datetime('now','-7 days')",(url,)).fetchone()
        if row:return row[0] if row[1]==200 else None
        if self.remaining<=0:return None
        self.remaining-=1
        try:
            response=requests.get(url,timeout=12,headers={'User-Agent':'AshevilleSoundcheck/1.0'},allow_redirects=False)
            if response.is_redirect:
                target=urljoin(url,response.headers.get('Location',''))
                return self.get(target) if target!=url else None
            status=response.status_code;markup=response.text[:2000000] if status==200 else ''
        except requests.RequestException:status=0;markup=''
        with connect(self.db_path) as c:c.execute('INSERT OR REPLACE INTO identity_page_cache VALUES(?,?,?,?)',(url,markup,status,utc_now()))
        return markup if status==200 else None


def discover(db_path,budget=40,artist_ids=None):
    reader=PageReader(db_path,budget);found=0
    with connect(db_path) as c:
        schema(c)
        rows=c.execute('''SELECT DISTINCT s.show_id,ss.source_url,a.artist_id,a.display_name FROM show_sources ss
            JOIN shows s USING(show_id) JOIN show_artists sa USING(show_id) JOIN artists a USING(artist_id)
            WHERE substr(s.performance_start,1,10)>=date('now') AND sa.billing_role LIKE '%headliner%'
            ORDER BY a.spotify_artist_id IS NOT NULL,s.performance_start''').fetchall()
    from concert_discovery.discovery import get_shows
    visible_ids={s['show_id'] for s in get_shows(db_path)}
    groups={}
    for row in rows:
        if row['show_id'] in visible_ids and (artist_ids is None or row['artist_id'] in artist_ids):groups.setdefault(row['source_url'],{})[row['display_name']]=row['artist_id']
    for url,artists in groups.items():
        markup=reader.get(url)
        if not markup:continue
        ids,pages=page_candidates(markup,list(artists),url)
        # Generic Listen buttons and embeds still need profile identity validation.
        from concert_discovery.spotify_matching import name_key
        from concert_discovery.spotify_public import fetch_public_artist_profile
        for sid in sorted(spotify_artist_ids(markup))[:4]:
            try:
                profile=fetch_public_artist_profile(sid)
                for name in artists:
                    if name_key(profile['name'])==name_key(name):ids[name].add(sid)
            except (requests.RequestException,ValueError,TypeError,RuntimeError,PermissionError):pass
        with connect(db_path) as c:
            for name,aid in artists.items():
                for sid in ids[name]:record(c,aid,sid,url,'Artist-associated event link');found+=1
                for page in pages[name]:c.execute('INSERT OR IGNORE INTO artist_source_pages VALUES(?,?)',(aid,page))
        for name,urls in pages.items():
            for page in sorted(urls)[:2]:
                content=reader.get(page)
                if not content:continue
                ids,_=page_candidates(content,[name],page,artist_page=True)
                with connect(db_path) as c:
                    for sid in ids[name]:record(c,artists[name],sid,page,'Source-linked artist page');found+=1
        if reader.remaining<=0:break
    # Provider-supplied artist URLs are also entry points, even without an event-page link.
    with connect(db_path) as c:
        saved=c.execute("SELECT DISTINCT p.*,a.display_name FROM artist_source_pages p JOIN artists a USING(artist_id) JOIN show_artists sa USING(artist_id) JOIN shows s USING(show_id) WHERE substr(s.performance_start,1,10)>=date('now') ORDER BY a.spotify_artist_id IS NOT NULL,s.performance_start").fetchall()
    for row in saved:
        if artist_ids is not None and row['artist_id'] not in artist_ids:continue
        content=reader.get(row['url'])
        if content:
            ids,_=page_candidates(content,[row['display_name']],row['url'],artist_page=True)
            with connect(db_path) as c:
                for sid in ids[row['display_name']]:record(c,row['artist_id'],sid,row['url'],'Provider-linked artist page');found+=1
        if reader.remaining<=0:break
    return {'source_candidates_found':found,'page_requests':budget-reader.remaining}


def apply_candidates(artist,db_path):
    from concert_discovery.spotify_matching import remember_source_identity,name_key
    from concert_discovery.spotify_public import fetch_public_artist_profile
    with connect(db_path) as c:
        schema(c);rows=c.execute('SELECT * FROM spotify_source_candidates WHERE artist_id=?',(artist['artist_id'],)).fetchall()
    ids={r['spotify_id'] for r in rows}
    if len(ids)!=1:return None  # Conflicts stay visible in the evidence table.
    sid=ids.pop()
    if artist.get('spotify_artist_id') and artist['spotify_artist_id']!=sid:return None
    profile=fetch_public_artist_profile(sid)
    exact=name_key(profile['name'])==name_key(artist['display_name'])
    lead_alias=bool(re.match(re.escape(profile['name'])+r'\s+(?:&|and)\s+',artist['display_name'],re.I))
    if not exact and not lead_alias:return None
    row=rows[0]
    return remember_source_identity(artist,profile,row['source_url'],row['method'],db_path)
