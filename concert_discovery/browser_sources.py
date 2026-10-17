"""Public calendar rendering, optional when Playwright is installed."""
from datetime import date,timedelta,datetime
import re
from concert_discovery.api_sources import event
from concert_discovery.event_sources import parse_performers
BIT_VENUES={
 'orange-peel':'10000275-the-orange-peel','grey-eagle':'10001131-the-grey-eagle',
 'asheville-music-hall':'10012070-asheville-music-hall','one-stop':'10005935-the-one-stop-at-asheville-music-hall',
 'eulogy':'10387643-eulogy','hellbender':'10608918-hellbender-by-the-orange-peel',
 'sierra-nevada':'10033253-sierra-nevada-brewing-co.'}
def fetch_browser_calendars(days=None,snapshots=None):
    from playwright.sync_api import sync_playwright
    rows=[];errors=[];end=(date.today()+timedelta(days=days)) if days is not None else date.max
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        for vid,slug in BIT_VENUES.items():
            try:
                page.goto('https://www.bandsintown.com/v/'+slug,wait_until='domcontentloaded',timeout=30000)
                page.locator('h1').wait_for(timeout=15000)
                more=page.get_by_role('button',name=re.compile('View more dates'))
                if more.count():more.click()
                cards=page.locator('a[href*="/e/"]').evaluate_all("""as=>as.map(a=>{let p=a;for(let i=0;i<6;i++){if(/^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\\s/.test(p.innerText.trim()))return {text:p.innerText,url:a.href};p=p.parentElement;if(!p)break;}return null;}).filter(Boolean)""")
                for card in cards:
                    parts=card['text'].split('\n');month=datetime.strptime(parts[0],'%b').month
                    day=date(date.today().year+(month<date.today().month),month,int(parts[1]))
                    if not date.today()<=day<=end:continue
                    title=parts[3];identity=card['url'].split('?')[0]
                    acts=parse_performers(title)
                    if not acts:continue
                    row=event('Bandsintown',identity,title,day.isoformat(),vid,acts,identity)
                    rows.append(row)
            except Exception:errors.append('Bandsintown '+vid+' unavailable; cached data retained.')
        try:
            from concert_discovery.sierra_calendar import fetch_api
            rows.extend(fetch_api(snapshots if days is None else None))
        except Exception as exc:
            errors.append('Sierra official API unavailable: '+str(exc)[:700])
        try:
            page.goto('https://sierranevada.com/events/mills-river',wait_until='domcontentloaded',timeout=30000)
            page.locator('.event-card').first.wait_for(timeout=15000)
            from concert_discovery.prices import save_sierra_card_prices
            save_sierra_card_prices(page.content())
        except Exception:
            errors.append('Sierra admission labels unavailable; existing prices retained.')
        for source,url in [('MusicHallOfficial','https://ashevillemusichall.com/all-shows/'),('OrangePeelOfficial','https://theorangepeel.net/events/?view=list'),('GreyEagleOfficial','https://www.thegreyeagle.com/calendar/')]:
            try:
                from concert_discovery.official_calendar import parse_calendar
                from concert_discovery.calendar_audit import collect_pages,snapshots as make_snapshots
                def load(page_url):
                    page.goto(page_url,wait_until='domcontentloaded',timeout=30000)
                    page.locator('#eventTitle').first.wait_for(timeout=20000)
                    return page.content()
                official,pages=collect_pages(url,load,lambda html:parse_calendar(html,days=days,source_name=source))
                rows.extend(official)
                if snapshots is not None and days is None:snapshots.extend(make_snapshots(official,url,pages))
            except Exception as error:errors.append(source+' browser calendar unavailable: '+str(error))
        try:
            page.goto('https://thirdroom.art/',wait_until='domcontentloaded',timeout=30000)
            page.locator('.seetickets-list-event-container').first.wait_for(timeout=20000)
            from concert_discovery.ticket_destinations import collect
            collect(page.content(),'https://thirdroom.art/')
        except Exception:errors.append('Third Room ticket links unavailable; saved destinations retained.')
        try:
            page.goto('https://185kingst.com/events/',wait_until='domcontentloaded',timeout=30000)
            page.locator('#eventTitle').first.wait_for(timeout=15000)
            from concert_discovery.ticket_destinations import collect_venue_schedule
            collect_venue_schedule(page.content(),'https://185kingst.com/events/','185-king-street','185 King Street')
        except Exception:errors.append('185 King Street ticket links unavailable; saved destinations retained.')
        try:
            from concert_discovery.discovery import get_shows
            from concert_discovery.prices import load as load_prices,for_show,from_ticket_markup,save
            from concert_discovery.ticketmaster_prices import event_id
            from concert_discovery.storage import connect,utc_now
            prices=load_prices();seen=set();checked=0
            with connect() as c:
                c.execute('CREATE TABLE IF NOT EXISTS ticketmaster_browser_checks(event_id TEXT PRIMARY KEY,checked_at TEXT,status TEXT)')
                recent={r[0] for r in c.execute("SELECT event_id FROM ticketmaster_browser_checks WHERE checked_at>=datetime('now','-7 days')")}
            for show in get_shows():
                if for_show(show,prices) or show.get('on_sale_label'):continue
                urls=[show.get('ticket_url')]+[s['source_url'] for s in show.get('sources',[])]
                ids={event_id(u) for u in urls if event_id(u)}
                if len(ids)!=1:continue
                eid=ids.pop()
                if eid in seen or eid in recent:continue
                if checked>=4:break
                seen.add(eid);checked+=1;outcome='unavailable'
                try:
                    url='https://www.ticketmaster.com/event/'+eid
                    page.goto(url,wait_until='domcontentloaded',timeout=30000)
                    notice=page.get_by_role('button',name='Accept & Continue',exact=True)
                    if notice.count():notice.click(timeout=3000)
                    quantity=page.get_by_role('button',name=re.compile('Open quantity filters'))
                    quantity.click(timeout=15000)
                    page.get_by_role('radio',name='Set quantity to: 1 Ticket',exact=True).check(timeout=5000)
                    page.get_by_role('menuitem').first.wait_for(timeout=10000)
                    price=from_ticket_markup(url,page.content(),selected_quantity=1)
                    if price:
                        for alias in [url]+[u for u in urls if event_id(u)==eid]:save({'source_url':alias,'source_name':'Ticketmaster rendered public inventory including resale'},price)
                        outcome='priced'
                except Exception:pass
                finally:
                    # A sold-out page has no quantity selector; save its explicit notice anyway.
                    try:
                        from concert_discovery.availability import record_ticket_page
                        record_ticket_page(url,page.content())
                    except Exception:pass
                with connect() as c:c.execute('INSERT OR REPLACE INTO ticketmaster_browser_checks VALUES(?,?,?)',(eid,utc_now(),outcome))
        except Exception:errors.append('Ticketmaster rendered prices unavailable; saved prices retained.')
        browser.close()
    return rows,errors
