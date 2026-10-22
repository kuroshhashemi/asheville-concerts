"""Small ordinary Chromium fallback; no stealth, proxies, seat holds or purchases."""
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit
from concert_discovery.storage import connect,DATABASE_PATH,utc_now
from concert_discovery.prices import load,for_show,from_ticket_markup,save,url_key

def refresh(db_path=DATABASE_PATH,limit=6,shows=None,backend="auto",priority_ids=None):
    import re
    from concert_discovery.discovery import get_shows
    from datetime import date
    from playwright.sync_api import sync_playwright
    shows=get_shows(db_path) if shows is None else shows
    shows=[s for s in shows if str(s.get('performance_start',''))[:10]>=date.today().isoformat()]
    prices=load();cutoff=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    hosts={'etix.com','tixr.com','secured.brevardmusic.org','jambase.com','wl.seetickets.us','wl.eventim.us','prod-nts-api.seeticketsusa.us','ticketmaster.com'}
    from pathlib import Path
    import os
    config={}
    private=next((root/'work/research/browserapi.env' for root in (Path(__file__).resolve().parents[2],Path(__file__).resolve().parents[3]) if (root/'work/research/browserapi.env').exists()),Path('/nonexistent'))
    if private.exists():
        for line in private.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);config[k.strip()]=v.strip().strip('\"\'')
    username=os.environ.get('BRIGHTDATA_BROWSER_USERNAME') or config.get('BRIGHTDATA_BROWSER_USERNAME')
    password=os.environ.get('BRIGHTDATA_BROWSER_PASSWORD') or config.get('BRIGHTDATA_BROWSER_PASSWORD')
    remote=bool(username and password) and backend!="ordinary"
    if backend=="remote" and not remote:return {"rendered_price_state":"not_configured"}
    table='cloud_rendered_price_checks' if remote else 'rendered_price_checks'
    blocked=set();seen=set();result={'rendered_price_pages':0,'rendered_prices_saved':0}
    with connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS '+table+'(url_key TEXT PRIMARY KEY,checked_at TEXT,status TEXT)')
        recent={r[0] for r in c.execute('SELECT url_key FROM '+table+" WHERE (status IN ('priced','sold_out') AND checked_at>=?) OR checked_at>=?",(cutoff,(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()))}
        # A failed event URL is not evidence that every event on this host is blocked.
    with sync_playwright() as p:
        chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if remote:
            from urllib.parse import quote
            from concert_discovery.brightdata_prices import reserve
            if not reserve(db_path):return {'rendered_price_state':'budget_reached'}
            try:
                browser=p.chromium.connect_over_cdp('wss://'+quote(username,safe='')+':'+quote(password,safe='')+'@brd.superproxy.io:9222')
            except Exception:
                # Playwright exceptions include the authenticated URL. Never propagate it.
                return {'rendered_price_state':'browser_connection_unavailable'}
        else:browser=p.chromium.launch(headless=True,**({'executable_path':str(chrome)} if chrome.exists() else {}))
        page=browser.new_page()
        page.route('**/*',lambda route:route.abort() if route.request.resource_type in ('image','media','font') else route.continue_())
        try:
            for show in sorted(shows,key=lambda s:(s['show_id'] not in priority_ids if priority_ids else False,not bool(s.get('just_announced')),s['performance_start'])):
                url=show.get('ticket_url') or '';host=(urlsplit(url).hostname or '').removeprefix('www.');key=url_key(url)
                if urlsplit(url).scheme!='https' or host not in hosts or key in seen or key in recent or for_show(show,prices) or show.get('sold_out') or show.get('on_sale_label'):continue
                if result['rendered_price_pages']>=limit:break
                seen.add(key);result['rendered_price_pages']+=1;outcome='unavailable'
                final_url=url;brevard_price=None
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=90000 if remote else 15000)
                    final_url=page.url
                    host=(urlsplit(final_url).hostname or '').removeprefix('www.')
                    if final_url!=url and host in hosts:
                        from concert_discovery.ticket_destinations import verified_show_link
                        with connect(db_path) as c:verified_show_link(c,show['show_id'],final_url,url)
                    if host=='etix.com':page.locator('[role="combobox"]').first.wait_for(timeout=10000)
                    elif host=='tixr.com':page.locator('.ticket[data-row-type="primary"] .info').first.wait_for(timeout=10000)
                    elif host=='ticketmaster.com':
                        page.locator('[role="menu"][aria-label^="Ticket listings"]').first.wait_for(state='attached',timeout=20000)
                        notice=page.get_by_role('button',name='Accept & Continue',exact=True)
                        if notice.count():notice.click(timeout=5000)
                        page.get_by_role('button',name=re.compile('Open quantity filters')).click(timeout=10000)
                        page.get_by_role('radio',name='Set quantity to: 1 Ticket',exact=True).check(timeout=10000)
                        page.get_by_role('menuitem').first.wait_for(timeout=15000)
                    elif host=='secured.brevardmusic.org':
                        from concert_discovery.brevard_pricing import collect
                        brevard_price=collect(page)
                    elif host in ('wl.seetickets.us','wl.eventim.us'):page.locator('#eventview select[id^="tt_"]').first.wait_for(timeout=30000)
                    else:page.locator('h1').first.wait_for(timeout=15000)
                    markup=page.content()
                    from concert_discovery.availability import record_ticket_page
                    record_ticket_page(url,markup,db_path)
                    if final_url!=url:record_ticket_page(final_url,markup,db_path)
                    from concert_discovery.source_links import schema,encode_markup
                    with connect(db_path) as c:
                        schema(c)
                        c.execute('INSERT OR REPLACE INTO identity_page_cache VALUES(?,?,?,?)',(url,encode_markup(markup),200,utc_now()))
                    price=brevard_price or from_ticket_markup(final_url,markup,selected_quantity=1 if host=='ticketmaster.com' else None)
                    if price:
                        save({'source_url':url,'source_name':'Rendered ticket provider'},price)
                        if final_url!=url:save({'source_url':final_url,'source_name':'Rendered ticket provider'},price)
                        result['rendered_prices_saved']+=1;outcome='priced'
                    else:
                        from concert_discovery.availability import access_condition,ticket_page_status
                        outcome=access_condition(final_url,markup) or ticket_page_status(final_url,markup) or 'unavailable'
                except Exception:
                    # Sold-out pages have no price selector. Preserve their explicit
                    # notice rather than treating that as a provider-wide failure.
                    from concert_discovery.availability import ticket_page_status,record_ticket_page
                    try:markup=page.content()
                    except Exception:markup=''
                    from concert_discovery.availability import access_condition
                    from concert_discovery.source_links import schema,encode_markup
                    if markup:
                        with connect(db_path) as c:
                            schema(c);c.execute('INSERT OR REPLACE INTO identity_page_cache VALUES(?,?,?,?)',(url,encode_markup(markup),200,utc_now()))
                    price=from_ticket_markup(final_url,markup,selected_quantity=1 if host=='ticketmaster.com' else None) if markup else None
                    status=ticket_page_status(final_url,markup) if markup else None
                    condition=access_condition(final_url,markup) if markup else None
                    if status:record_ticket_page(final_url,markup,db_path)
                    if price:
                        save({'source_url':url,'source_name':'Rendered ticket provider'},price)
                        result['rendered_prices_saved']+=1;outcome='priced'
                    else:outcome=condition or status or 'blocked_or_unavailable'
                with connect(db_path) as c:c.execute('INSERT OR REPLACE INTO '+table+' VALUES(?,?,?)',(key,utc_now(),outcome))
        finally:browser.close()
    return result
