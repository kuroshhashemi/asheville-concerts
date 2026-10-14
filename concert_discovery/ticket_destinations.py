"""Retain source-verified public ticket destinations by provider event identity."""
import re,base64
from urllib.parse import urlsplit,urlunsplit,unquote
from concert_discovery.storage import connect,utc_now,DATABASE_PATH

def identity(url):
    p=urlsplit(url or '')
    if p.hostname=='prod-nts-api.seeticketsusa.us':
        m=re.search(r'/promote/([^/]+)/',p.path)
        if m:
            try:
                text=base64.b64decode(m[1]+'='*((-len(m[1]))%4)).decode()
                return re.search(r'STUS-(\d+)',text)[1]
            except (ValueError,TypeError,AttributeError):return None
    if p.hostname in ('wl.seetickets.us','wl.eventim.us'):
        m=re.search(r'/(\d{5,})/?$',p.path)
        return m[1] if m else None

def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS provider_ticket_links(event_id TEXT PRIMARY KEY,url TEXT,source_url TEXT,checked_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS official_ticket_links(show_id INTEGER PRIMARY KEY,url TEXT,source_url TEXT,checked_at TEXT)')

def verified_show_link(c,show_id,url,source_url):
    schema(c)
    c.execute('INSERT OR REPLACE INTO official_ticket_links VALUES(?,?,?,?)',(show_id,url,source_url,utc_now()))
    c.execute('UPDATE shows SET ticket_url=? WHERE show_id=?',(url,show_id))

def retain_verified_link(c,show_id,incoming):
    schema(c)
    p=urlsplit(incoming or '')
    row=c.execute('SELECT url,source_url FROM official_ticket_links WHERE show_id=?',(show_id,)).fetchone()
    if row and (p.path.rstrip('/') in ('','/events','/events-tickets','/calendar') or incoming==row[1]):return row[0]
    return incoming

def resolve(c,url):
    p=urlsplit(url or '')
    if p.hostname=='etix.prf.hn' and '/destination:' in p.path:
        target=unquote(p.path.split('/destination:',1)[1])
        if urlsplit(target).scheme=='https' and urlsplit(target).hostname in ('www.etix.com','etix.com'):return target
    schema(c);ident=identity(url)
    row=c.execute('SELECT url FROM provider_ticket_links WHERE event_id=?',(ident,)).fetchone() if ident else None
    return row[0] if row else url

def collect(markup,source_url,db_path=DATABASE_PATH):
    from concert_discovery.official_calendar import Tree
    tree=Tree();tree.feed(markup);found=0
    with connect(db_path) as c:
        schema(c)
        for n in tree.root.walk():
            url=n.attrs.get('href','') if n.tag=='a' else ''
            if not url.startswith('https://'):continue
            ident=identity(url)
            if ident and urlsplit(url).hostname in ('wl.seetickets.us','wl.eventim.us'):
                if urlsplit(url).hostname=='wl.seetickets.us':
                    p=urlsplit(url);url=urlunsplit((p.scheme,'wl.eventim.us',p.path,p.query,p.fragment))
                c.execute('INSERT OR REPLACE INTO provider_ticket_links VALUES(?,?,?,?)',(ident,url,source_url,utc_now()));found+=1
        for r in c.execute('SELECT show_id,ticket_url FROM shows').fetchall():
            new=resolve(c,r['ticket_url'])
            if new!=r['ticket_url']:c.execute('UPDATE shows SET ticket_url=? WHERE show_id=?',(new,r['show_id']))
    venue_cards(tree,source_url,db_path)
    return found

def venue_cards(tree,source_url,db_path):
    """Repair generic venue links using a unique official bill and calendar date."""
    if (urlsplit(source_url).hostname or '').removeprefix('www.')!='thirdroom.art':return
    from datetime import datetime
    from concert_discovery.event_sources import normalize
    from concert_discovery.prices import load,url_key,save
    prices=load()
    with connect(db_path) as c:
        shows=c.execute("SELECT show_id,title,performance_start,ticket_url FROM shows WHERE venue_id IN (SELECT venue_id FROM venues WHERE name='Third Room')").fetchall()
        for card in tree.root.walk():
            if not card.has('seetickets-list-event-container'):continue
            nodes=list(card.walk())
            head=next((n.text() for n in nodes if n.has('headliners')),None)
            day=next((n.text() for n in nodes if n.has('date')),None)
            dest=next((n.attrs.get('href') for n in nodes if n.tag=='a' and identity(n.attrs.get('href',''))),None)
            if not head or not day or not dest:continue
            try:md=datetime.strptime(day.strip(),'%a %b %d').strftime('%m-%d')
            except ValueError:continue
            candidates=[s for s in shows if s['performance_start'][5:10]==md and len(normalize(head))>=4 and normalize(s['title']).startswith(normalize(head))]
            if len(candidates)!=1:continue
            show=candidates[0];dest=resolve(c,dest)
            old=urlsplit(show['ticket_url'] or '')
            if (old.hostname or '').removeprefix('www.')=='thirdroom.art' and old.path.rstrip('/') in ('','/calendar'):
                verified_show_link(c,show['show_id'],dest,source_url)
            amount=next((n.text() for n in nodes if n.has('price')),None)
            # A provider total already collected takes precedence over venue base prices.
            if amount and url_key(dest) not in prices:
                values=[float(v.replace(',','')) for v in re.findall(r'\$([\d,]+(?:\.\d{1,2})?)',amount)]
                if values:save({'source_url':dest,'source_name':'Official venue ticket card'},{'min':min(values),'max':max(values),'includes_fees':False})

def event_page(markup,url,db_path=DATABASE_PATH):
    if urlsplit(url).hostname not in ('www.harrahscherokeecenterasheville.com','www.brevardmusic.org','sierranevada.com','www.sierranevada.com'):return
    from concert_discovery.official_calendar import Tree
    tree=Tree();tree.feed(markup)
    candidates={n.attrs.get('href') for n in tree.root.walk() if n.tag=='a' and n.text().strip().casefold() in ('buy tickets','get tickets','purchase tickets') and n.attrs.get('href','').startswith('https://')}
    # Site-wide navigation is not a ticket destination for this event.
    candidates={u for u in candidates if urlsplit(u).path.rstrip('/') not in ('/events','/events-tickets')}
    if len(candidates)==1:
        dest=candidates.pop()
        with connect(db_path) as c:
            for r in c.execute('SELECT show_id FROM shows WHERE official_event_url=?',(url,)).fetchall():
                verified_show_link(c,r['show_id'],dest,url)
