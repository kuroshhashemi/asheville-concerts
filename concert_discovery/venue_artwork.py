"""Cached favicon discovery for venues; runs during collection, never browsing."""
import base64
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse
import requests
from html.parser import HTMLParser

class IconParser(HTMLParser):
    def __init__(self):super().__init__();self.icons=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="link" and "icon" in a.get("rel", "").lower() and a.get("href"):self.icons.append(a["href"])
from concert_discovery.storage import connect, utc_now

def saved_icons():
    return {'revival':'data:image/webp;base64,'+base64.b64encode((Path(__file__).parent/'assets/revival.webp').read_bytes()).decode()}

def refresh(db_path=None, limit=25):
    now=datetime.now(timezone.utc)
    with connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS venue_icon_checks (venue_id TEXT PRIMARY KEY, status TEXT, checked_at TEXT, detail TEXT)')
        c.executemany('INSERT OR REPLACE INTO venue_icons SELECT ?,? WHERE EXISTS(SELECT 1 FROM venues WHERE venue_id=?)',[(k,v,k) for k,v in saved_icons().items()])
        rows=[dict(r) for r in c.execute('''SELECT v.venue_id,v.official_url,h.checked_at FROM venues v
          LEFT JOIN venue_icons i USING(venue_id) LEFT JOIN venue_icon_checks h USING(venue_id)
          WHERE COALESCE(i.icon_url,'')='' ORDER BY h.checked_at IS NOT NULL,h.checked_at,v.venue_id''')]
    attempted=0
    for row in rows:
        if row['checked_at'] and now-datetime.fromisoformat(row['checked_at'])<timedelta(days=1):continue
        if attempted>=limit:break
        attempted+=1;status='unavailable';detail='Website supplied no usable favicon';icon=None
        try:
            url=row['official_url']
            if urlparse(url or '').scheme not in ('http','https'):detail='No venue website available'
            else:
                response=requests.get(url,timeout=12);response.raise_for_status()
                parser=IconParser();parser.feed(response.text)
                candidates=[urljoin(response.url,href) for href in parser.icons]+[urljoin(response.url,'/favicon.ico')]
                for candidate in dict.fromkeys(candidates):
                    if urlparse(candidate).scheme not in ('http','https'):continue
                    r=requests.get(candidate,timeout=12)
                    if r.ok and r.content and r.headers.get('Content-Type','').lower().startswith('image/'):
                        icon=candidate;status='complete';detail='Favicon verified from venue website';break
        except requests.RequestException:status='blocked';detail='Venue website or icon request failed'
        with connect(db_path) as c:
            if icon:c.execute('INSERT OR REPLACE INTO venue_icons VALUES(?,?)',(row['venue_id'],icon))
            c.execute('INSERT OR REPLACE INTO venue_icon_checks VALUES(?,?,?,?)',(row['venue_id'],status,utc_now(),detail))
    return {'venue_icon_requests':attempted}
