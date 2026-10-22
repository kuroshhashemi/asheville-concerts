"""Owner-only pricing diagnostics from saved evidence. Never fetches ticket pages."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from concert_discovery.storage import connect
from concert_discovery.prices import load, for_show, url_key


def report(shows, prices=None, db_path=None):
    prices=load() if prices is None else prices
    attempts={};pages={}
    with connect(db_path) as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('ticket_price_checks','brightdata_price_checks','rendered_price_checks','cloud_rendered_price_checks','ticketmaster_price_checks'):
            if table not in tables:continue
            for row in c.execute('SELECT * FROM '+table):
                r=dict(row);key=r.get('url_key') or r.get('event_id');r['collector']=table
                attempts.setdefault(key,[]).append(r)
        if 'identity_page_cache' in tables:
            pages={url_key(r['url']):dict(r) for r in c.execute('SELECT url,status,markup,checked_at FROM identity_page_cache')}
    counts=Counter();rows=[]
    from concert_discovery.ticketmaster_prices import event_id
    from concert_discovery.source_links import decode_markup
    for show in shows:
        price=for_show(show,prices)
        state='Resale' if price and price.get('resale_only') else 'Sold Out' if show.get('sold_out') else 'Not yet on sale' if show.get('on_sale_label') else 'Price / Free' if price is not None else 'Missing price'
        counts[state]+=1
        if state not in ('Missing price','Not yet on sale'):continue
        urls=[show.get('ticket_url'),show.get('official_event_url')]+[s['source_url'] for s in show.get('sources',[])]
        keys={url_key(u) for u in urls if u};keys.update(event_id(u) for u in urls if event_id(u))
        checks=[a for k in keys for a in attempts.get(k,[])];latest=max(checks,key=lambda r:r.get('checked_at',''),default={})
        cached=[pages[k] for k in keys if k in pages]
        page=max(cached,key=lambda r:r.get('checked_at',''),default={})
        status=latest.get('status');http=latest.get('http_status',page.get('status'))
        try:markup=decode_markup(page.get('markup','')).casefold()
        except (ValueError,TypeError):markup=''
        if state=='Not yet on sale':reason='Not on sale yet';detail=show['on_sale_label']
        elif status=='password_required' or 'a password is required to buy tickets' in markup:reason='Password required';detail='Sales are restricted; recheck daily for public access.'
        elif status=='available':reason='Price extraction failed';detail='Tickets were available, but no usable adult price was extracted.'
        elif 'tickets are not available' in markup:reason='Tickets unavailable';detail='Provider does not explain whether sold out or not on sale.'
        elif http in (202,403,429) or status in ('blocked','blocked_or_unavailable') or any(t in markup for t in ("confirm you're not a bot",'please verify you are a human')):reason='Access blocked';detail='Automated request could not read the ticket page.'
        elif status in ('failed','error','unavailable') and http!=200:reason='Collection failed';detail='Request or provider service failed; no price inferred.'
        elif status=='no_supported_adult_offer':reason='No eligible inventory';detail='No supported adult primary offer; resale may still exist.'
        elif status=='priced':reason='Saved price missing';detail='A check succeeded, but its saved price is absent for this show.'
        elif cached or status=='unavailable':reason='No price found';detail='Page checked; no supported price extracted.'
        else:reason='Not checked';detail='No saved ticket-price attempt for this destination.'
        checked=latest.get('checked_at') or page.get('checked_at');retry=None
        if state=='Not yet on sale':retry=show.get('on_sale_at')
        elif checked:
            days=1
            try:retry=(datetime.fromisoformat(checked.replace('Z','+00:00'))+timedelta(days=days)).isoformat()
            except ValueError:pass
        def display_time(value):
            if not value:return '—'
            from zoneinfo import ZoneInfo
            try:
                d=datetime.fromisoformat(value.replace('Z','+00:00'))
                if d.tzinfo is None:d=d.replace(tzinfo=ZoneInfo('America/New_York'))
                return d.astimezone(ZoneInfo('America/New_York')).strftime('%b %d, %I:%M %p')
            except ValueError:return value
        rows.append({'Date':show['performance_start'][:10],'Show':show['title'],'Venue':show['venue_name'],'Reason':reason,'Detail':detail,'Last checked (ET)':display_time(checked),'Retry eligible (ET)':display_time(retry),'Tickets':show.get('ticket_url') or show.get('official_event_url')})
    return dict(counts),rows


def admin_view(st,identity,owner_email,shows,db_path=None):
    from concert_discovery.activity import is_owner
    if not is_owner(identity,owner_email):return
    with st.expander('Pricing gaps · owner only'):
        counts,rows=report(shows,db_path=db_path)
        st.caption('All upcoming shows, independent of your filters. Sold Out and Resale are resolved ticket states. This view makes no collection requests.')
        st.write(' · '.join(f'{counts.get(k,0)} {k}' for k in ('Price / Free','Sold Out','Resale','Not yet on sale','Missing price')))
        if rows:
            reasons=Counter(r['Reason'] for r in rows)
            st.caption(' · '.join(f'{reason}: {count}' for reason,count in sorted(reasons.items())))
            st.dataframe(rows,hide_index=True,width='stretch',column_config={'Tickets':st.column_config.LinkColumn('Tickets')})
            st.caption('Retry eligible is the earliest a collector may retry; its next scheduled run and request budget determine when it actually does.')
        else:st.caption('No unresolved pricing gaps.')
