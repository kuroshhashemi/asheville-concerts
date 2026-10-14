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
        browser.close()
    return rows,errors
