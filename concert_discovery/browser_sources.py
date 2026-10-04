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
def fetch_browser_calendars(days=None):
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
            page.goto('https://sierranevada.com/events/mills-river',wait_until='domcontentloaded',timeout=30000)
            page.get_by_role('group',name='event',exact=True).first.wait_for(timeout=20000)
            cards=page.get_by_role('group',name='event',exact=True).evaluate_all("""xs=>xs.map(x=>({title:x.querySelector('h3')?.innerText,text:x.innerText,url:x.querySelector('a')?.href}))""")
            for card in cards:
                m=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})',card['text'])
                if not m or not card['title']:continue
                month=datetime.strptime(m[1],'%B').month;day=date(date.today().year+(month<date.today().month),month,int(m[2]))
                if not date.today()<=day<=end:continue
                acts=parse_performers(card['title'])
                if not acts:continue
                row=event('SierraOfficial',card['url'],card['title'],day.isoformat(),'sierra-nevada',acts,card['url'])
                row['official_event_url']=card['url'];row['date_status']='venue_confirmed';rows.append(row)
        except Exception:errors.append('Sierra official browser calendar unavailable.')
        browser.close()
    return rows,errors
