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
    # Public onsale only: donor/subscriber presales are separate offers.
    if (urlsplit(url).hostname or '').endswith('brevardmusic.org'):
        m=re.search(r'Public Onsale:\s*([A-Za-z]+)\s+(\d{1,2})(?:,?\s+(20\d\d))?',tree.root.text(),re.I)
        if m:
            from datetime import datetime
            from concert_discovery.availability import save_sale
            try:day=datetime.strptime(str(m[3] or datetime.now().year)+' '+m[1]+' '+m[2],'%Y %B %d').date().isoformat()
            except ValueError:day=None
            if day:
                with connect(db_path) as c:
                    for r in c.execute('SELECT show_id FROM shows WHERE official_event_url=?',(url,)).fetchall():save_sale(c,r['show_id'],day,url)
    candidates={n.attrs.get('href') for n in tree.root.walk() if n.tag=='a' and n.text().strip().casefold() in ('buy tickets','get tickets','purchase tickets') and n.attrs.get('href','').startswith('https://')}
    # Site-wide navigation is not a ticket destination for this event.
    candidates={u for u in candidates if urlsplit(u).path.rstrip('/') not in ('/events','/events-tickets')}
    if len(candidates)==1:
        dest=candidates.pop()
        with connect(db_path) as c:
            for r in c.execute('SELECT show_id FROM shows WHERE official_event_url=?',(url,)).fetchall():
                verified_show_link(c,r['show_id'],dest,url)


def collect_venue_schedule(markup, source_url, venue_id, venue_name, db_path=DATABASE_PATH):
    """Resolve existing supplemental shows by venue, calendar day and performer.

    Never adds shows or copies one date's ticket link onto another date.
    """
    from concert_discovery.official_calendar import parse_calendar
    from concert_discovery.event_sources import normalize
    from concert_discovery.prices import save
    events=parse_calendar(markup,source_name='SupplementalOfficial',venue_default=venue_name)
    changed=0
    with connect(db_path) as c:
        shows=[dict(r) for r in c.execute('SELECT * FROM shows WHERE venue_id=?',(venue_id,))]
        for event in events:
            ticket=event.get('ticket_url')
            if not ticket:continue
            day=event['performance_start'][:10];title=normalize(event['title'])
            candidates=[]
            for show in shows:
                if show['performance_start'][:10]!=day:continue
                names=[normalize(r[0]) for r in c.execute("SELECT a.display_name FROM artists a JOIN show_artists sa USING(artist_id) WHERE sa.show_id=? AND sa.billing_role LIKE '%headliner%'",(show['show_id'],))]
                if any(len(n)>=4 and re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',title) for n in names):candidates.append(show)
            if len(candidates)!=1:continue
            show=candidates[0];verified_show_link(c,show['show_id'],ticket,source_url);changed+=1
            if event.get('advertised_price'):save({'source_url':ticket,'source_name':'Official venue calendar'},event['advertised_price'])
    return changed


def reconcile_ticketmaster(events, db_path=DATABASE_PATH):
    """Repair artist-page links from exact attraction identity + day + venue.

    Uses an existing Discovery response, never another API request. Multi-day
    passes and different dates cannot replace a single show's destination.
    """
    from concert_discovery.event_sources import venue_id_for
    from concert_discovery.ticketmaster_prices import event_id
    from concert_discovery.availability import save_sale
    changed=0
    with connect(db_path) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='shows'").fetchone():return 0
        shows=[dict(r) for r in c.execute('SELECT * FROM shows')]
        for event in events:
            url=event.get('url','');eid=event_id(url)
            if not eid:continue
            day=event.get('dates',{}).get('start',{}).get('localDate')
            venues=event.get('_embedded',{}).get('venues',[])
            if not day or not venues:continue
            v=venues[0];name=v.get('name','');vid=venue_id_for(name)
            attractions={urlsplit(a.get('url','')).path for a in event.get('_embedded',{}).get('attractions',[]) if a.get('url')}
            candidates=[]
            for show in shows:
                if show['performance_start'][:10]!=day:continue
                same_venue=show['venue_id']==vid or ('harrah' in name.lower() and 'asheville' in name.lower() and show['venue_id'] in ('harrahs-arena','thomas-wolfe'))
                if not same_venue:continue
                sources=[r[0] for r in c.execute('SELECT source_url FROM show_sources WHERE show_id=?',(show['show_id'],))]
                links=[show.get('ticket_url') or '']+sources
                if any(event_id(u)==eid for u in links) or urlsplit(show.get('ticket_url') or '').path in attractions:
                    candidates.append(show)
            if len(candidates)!=1:continue
            show=candidates[0]
            c.execute('INSERT OR REPLACE INTO show_sources VALUES(?,?,?,?,?,?,?)',('Ticketmaster:'+event['id'],show['show_id'],'Ticketmaster',event['id'],url,name,utc_now()))
            if event_id(show.get('ticket_url')) is None:
                verified_show_link(c,show['show_id'],url,url);changed+=1
            save_sale(c,show['show_id'],event.get('sales',{}).get('public',{}).get('startDateTime'),url)
    return changed
