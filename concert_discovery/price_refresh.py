"""Bounded ticket-page price checks, shared across scheduled refreshes.

No browser challenge workarounds or paid endpoints. Existing calendar/API prices
remain usable when a ticket provider blocks access. Failed checks retry daily.
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from concert_discovery.storage import connect, DATABASE_PATH, utc_now
from concert_discovery.prices import load, for_show, from_ticket_markup, save, url_key
from concert_discovery.source_links import PageReader, schema as page_schema, decode_markup

PROVIDERS={'etix.com','tixr.com','dice.fm','link.dice.fm','eventbrite.com','sierranevada.com',
           '185kingst.com','brevardmusic.org','highlandbrewing.com',
           'secured.brevardmusic.org','prod-nts-api.seeticketsusa.us','wl.eventim.us','harrahscherokeecenterasheville.com'}

def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS ticket_price_checks(
      url_key TEXT PRIMARY KEY,url TEXT NOT NULL,checked_at TEXT NOT NULL,
      status TEXT NOT NULL,http_status INTEGER,detail TEXT NOT NULL)''')

def refresh(db_path=DATABASE_PATH,limit=12,shows=None,force=False,priority_ids=None):
    from concert_discovery.discovery import get_shows
    shows=get_shows(db_path) if shows is None else shows
    prices=load();reader=PageReader(db_path,budget=limit);cutoff=(datetime.now(timezone.utc)-timedelta(days=0 if force else 1)).isoformat()
    result={'price_page_requests':0,'price_pages_checked':0,'price_pages_priced':0,'price_providers_blocked':[]}
    blocked=set();seen=set()
    with connect(db_path) as c:
        schema(c)
        blocked.update((urlsplit(r['url']).hostname or '').removeprefix('www.') for r in c.execute(
          "SELECT url FROM ticket_price_checks WHERE status IN ('blocked','error') AND checked_at>=?",(cutoff,)))
    # Unknown prices first, then oldest known ones; shared URLs checked once.
    shows=sorted(shows,key=lambda s:(s['show_id'] not in priority_ids if priority_ids else False,for_show(s,prices) is not None,not bool(s.get('just_announced')),s.get('performance_start','')))
    for show in shows:
        if show.get('on_sale_label'):continue
        url=show.get('ticket_url') or ''
        host=(urlsplit(url).hostname or '').removeprefix('www.')
        if host.endswith('.eventbrite.com'):host='eventbrite.com'
        official=show.get('official_event_url') or ''
        if host not in PROVIDERS and (urlsplit(official).hostname or '').removeprefix('www.')=='harrahscherokeecenterasheville.com':
            url=official;host='harrahscherokeecenterasheville.com'
        if host not in PROVIDERS or host in blocked or urlsplit(url).scheme!='https':continue
        key=url_key(url)
        if key in seen:continue
        seen.add(key)
        with connect(db_path) as c:
            schema(c);page_schema(c)
            checked=c.execute('SELECT checked_at,status FROM ticket_price_checks WHERE url_key=?',(key,)).fetchone()
            if checked and checked['checked_at']>=cutoff and (checked['status']!='priced' or for_show(show,prices) is not None):continue
            cached=c.execute('SELECT * FROM identity_page_cache WHERE url=? AND checked_at>=?',(url,cutoff)).fetchone()
        if cached:
            markup=decode_markup(cached['markup']) if cached['status']==200 else None
            status=cached['status'];checked_at=cached['checked_at']
        else:
            if reader.remaining<=0:break
            markup=reader.get(url)
            with connect(db_path) as c:
                cached=c.execute('SELECT * FROM identity_page_cache WHERE url=?',(url,)).fetchone()
            status=200 if markup else cached['status'] if cached else 0
            checked_at=cached['checked_at'] if cached else utc_now()
            # A redirect chain can consume the remaining budget. Leave it pending,
            # rather than incorrectly recording the provider as inaccessible.
            if not markup and reader.remaining<=0 and (status==0 or 300<=status<400):break
        if host=='sierranevada.com' and markup:
            with connect(db_path) as c:
                repaired=c.execute('SELECT ticket_url FROM shows WHERE show_id=?',(show.get('show_id'),)).fetchone()
            if repaired and repaired[0]!=url and (urlsplit(repaired[0]).hostname or '').endswith('eventbrite.com') and reader.remaining>0:
                target=repaired[0];ticket_markup=reader.get(target)
                if ticket_markup:
                    price=from_ticket_markup(target,ticket_markup)
                    if price:save({'source_url':target,'source_name':'Eventbrite fee-inclusive ticket price'},price)
        if markup:
            from concert_discovery.ticket_destinations import event_page
            event_page(markup,url,db_path)
            from concert_discovery.availability import record_ticket_page
            record_ticket_page(url,markup,db_path,checked_at)
        price=from_ticket_markup(url,markup) if markup else None
        if price:
            save({'source_url':url,'source_name':'Ticket provider advertised price','price_observed_at':checked_at},price)
            outcome='priced';detail='Explicit event ticket price';result['price_pages_priced']+=1
        elif status in (202,403,429):
            outcome='blocked';detail='Provider access unavailable';blocked.add(host)
        elif status==200:
            outcome='unavailable';detail='No usable event ticket price in response'
        else:
            outcome='error';detail='Ticket page could not be retrieved'
            blocked.add(host) # Stop repeated failures for this provider in this run.
        with connect(db_path) as c:
            c.execute('INSERT OR REPLACE INTO ticket_price_checks VALUES(?,?,?,?,?,?)',(key,url,checked_at,outcome,status,detail))
        result['price_pages_checked']+=1
    result['price_page_requests']=limit-reader.remaining
    result['price_providers_blocked']=sorted(blocked)
    return result
