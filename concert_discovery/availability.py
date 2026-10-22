"""Explicit ticket availability only; missing evidence remains unknown."""
import re

def text_availability(text):
    if re.search(r"\bsold[\s-]*out\b", text, re.I): return 'sold_out'
    return None

def structured_availability(event):
    offers=event.get('offers',[])
    if isinstance(offers,dict):offers=[offers]
    states=[o.get('availability','').rstrip('/').rsplit('/',1)[-1] for o in offers if isinstance(o,dict)]
    if states and all(s=='SoldOut' for s in states):return 'sold_out'
    if 'InStock' in states or 'LimitedAvailability' in states:return 'available'
    return None

def ticket_page_status(url,markup):
    """Provider-scoped evidence, excluding artist bios and related-event upsells."""
    from urllib.parse import urlsplit
    from concert_discovery.official_calendar import Tree
    host=(urlsplit(url).hostname or '').removeprefix('www.')
    t=Tree();t.feed(markup)
    if host=='etix.com':
        if any(n.tag in ('p','span','div') and re.fullmatch(r'This performance is sold[ -]out\.?',n.text().strip(),re.I) for n in t.root.walk()):return 'sold_out'
        if any(n.attrs.get('role')=='combobox' and 'Price:' in n.attrs.get('aria-label','') and n.attrs.get('aria-disabled')!='true' and 'disabled' not in n.attrs for n in t.root.walk()):return 'available'
    elif host=='ticketmaster.com':
        # Only actual ticket-list offers or explicit current-event notices.
        menus=[n for n in t.root.walk() if n.attrs.get('role')=='menu' and n.attrs.get('aria-label','').startswith('Ticket listings')]
        if any(n.tag=='button' and re.search(r'Select (?:Verified Resale Ticket|Standard Admission|Official Platinum)',n.text()) for root in menus for n in root.walk()):return 'available'
        if any(n.tag in ('p','h1','h2','h3') and re.fullmatch(r'(?:This event is |This show is |All tickets (?:are )?)?sold[ -]out[.!]?',n.text().strip(),re.I) for n in t.root.walk()):return 'sold_out'
    elif host=='tixr.com':
        tickets=[n for n in t.root.walk() if n.has('ticket') and n.attrs.get('data-row-type')=='primary']
        if any(n.attrs.get('data-product-state')=='OPEN' for n in tickets):return 'available'
        if tickets and all(n.attrs.get('data-product-state') in ('QUEUED','SOLD_OUT') for n in tickets) and any(re.search(r'\bwaitlist\b|\bsold out\b',n.text(),re.I) for n in tickets):return 'sold_out'
    elif host in ('wl.eventim.us','wl.seetickets.us'):
        root=next((n for n in t.root.walk() if n.attrs.get('id')=='eventview' or (n.attrs.get('id')=='main' and n.has('event-pg'))),None)
        if root:
            def scoped(n):
                if n.attrs.get('id','').startswith('addtomyorder') or n.has('after-event-recommendations'):return
                yield n
                for child in n.children:
                    if hasattr(child,'attrs'):yield from scoped(child)
            nodes=list(scoped(root))
            if any(n.has('sold-out-info-box') and re.search(r'Tickets are not available',n.text(),re.I) for n in nodes):return 'sold_out'
            if any(n.tag=='select' and n.attrs.get('id','').startswith('tt_') and 'disabled' not in n.attrs for n in nodes):return 'available'
            if any(n.tag in ('span','p','div') and not any(d.attrs.get('id','').startswith('addtomyorder') for d in n.walk()) and re.fullmatch(r'(?:This event is )?sold[ -]out[.!]?',n.text().strip(),re.I) for n in nodes):return 'sold_out'
    return None

def record_ticket_page(url,markup,db_path=None,observed_at=None):
    from concert_discovery.storage import connect,DATABASE_PATH,utc_now
    from concert_discovery.prices import url_key
    from concert_discovery.ticket_destinations import identity
    status=ticket_page_status(url,markup)
    if not status:return 0
    key=url_key(url);ident=identity(url);count=0
    with connect(db_path or DATABASE_PATH) as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'shows','show_sources','ticket_availability'}<=tables:return 0
        candidates=c.execute('SELECT show_id,ticket_url AS url FROM shows UNION SELECT show_id,source_url AS url FROM show_sources').fetchall()
        ids={r['show_id'] for r in candidates if url_key(r['url'])==key or (ident and identity(r['url'])==ident)}
        for sid in ids:
            c.execute('''INSERT INTO ticket_availability VALUES(?,?,?,?,?)
                ON CONFLICT(source_key) DO UPDATE SET status=excluded.status,
                source_url=excluded.source_url, observed_at=excluded.observed_at
                WHERE excluded.observed_at>=ticket_availability.observed_at''',
                ('ticket-page:'+str(sid)+':'+key,sid,status,url,observed_at or utc_now()));count+=1
    return count


def sale_schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS ticket_sale_windows(show_id INTEGER PRIMARY KEY,on_sale_at TEXT,source_url TEXT,observed_at TEXT)')


def save_sale(c, show_id, on_sale_at, source_url):
    if not on_sale_at:return
    from datetime import datetime
    try:datetime.fromisoformat(on_sale_at.replace('Z','+00:00'))
    except ValueError:return
    from concert_discovery.storage import utc_now
    sale_schema(c)
    c.execute('INSERT OR REPLACE INTO ticket_sale_windows VALUES(?,?,?,?)',(show_id,on_sale_at,source_url,utc_now()))


def future_sale_label(value):
    from datetime import datetime,timezone
    if not value:return None
    try:
        date=datetime.fromisoformat(value.replace('Z','+00:00'))
        if date.tzinfo is None:
            from zoneinfo import ZoneInfo
            date=date.replace(tzinfo=ZoneInfo('America/New_York'))
        if date<=datetime.now(timezone.utc):return None
        return f'On Sale {date.month}/{date.day}'
    except ValueError:return None

def access_condition(url,markup):
    from urllib.parse import urlsplit
    from concert_discovery.official_calendar import Tree
    host=(urlsplit(url).hostname or '').removeprefix('www.')
    tree=Tree();tree.feed(markup)
    if host in ('wl.eventim.us','wl.seetickets.us') and any(n.tag=='form' and n.attrs.get('id')=='eventpassform' for n in tree.root.walk()):return 'password_required'
    if 'queue-it' in markup.lower() and host=='secured.brevardmusic.org':return 'waiting_room'
    return None
