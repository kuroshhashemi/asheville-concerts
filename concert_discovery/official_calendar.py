"""Ordinary public Orange Peel calendar collection, including Hellbender bills."""
from datetime import date, timedelta
from html.parser import HTMLParser
import re
import json
from datetime import datetime
import requests
from concert_discovery.event_sources import parse_performers, normalize,venue_id_for

class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    def text(self):
        return ' '.join(c.text() if isinstance(c, Node) else c for c in self.children).strip()
    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk()
    def has(self, cls):
        return cls in self.attrs.get('class', '').split()

class Tree(HTMLParser):
    def __init__(self):
        super().__init__(); self.root = Node(); self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs); self.stack[-1].children.append(n)
        if tag not in {'img','input','br','hr','meta','link','source','area','wbr'}:
            self.stack.append(n)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def parse_calendar(html, today=None, days=None,source_name='OrangePeelOfficial'):
    today = today or date.today(); end = (today + timedelta(days=days)) if days is not None else date.max
    p = Tree(); p.feed(html); events = {}
    def scoped_nodes(node, year=None):
        # Month headers belong to their layout container, not the whole document.
        yield node, year
        for child in node.children:
            if not isinstance(child, Node): continue
            if child.has('rhp-events-list-separator-month'):
                m = re.search(r'\b(20\d\d)\b', child.text())
                if m: year = int(m.group(1))
            yield from scoped_nodes(child, year)
    for n, year in scoped_nodes(p.root):
        if not n.has('eventWrapper'):
            continue
        nodes = list(n.walk())
        title_node = next((x for x in nodes if x.attrs.get('id') == 'eventTitle'), None)
        date_node = next((x for x in nodes if x.attrs.get('id') == 'eventDate'), None)
        venue_node = next((x for x in nodes if x.has('venueLink')), None)
        if not all((title_node, date_node, venue_node)):
            continue
        raw_date = re.search(r'([A-Za-z]{3})\s+(\d{1,2})', date_node.text())
        if not raw_date: continue
        import datetime
        event_year=year or today.year
        show_date = datetime.datetime.strptime(f'{event_year} {raw_date.group(1)} {raw_date.group(2)}', '%Y %b %d').date()
        if year is None and show_date.month<today.month:show_date=show_date.replace(year=today.year+1)
        weekday = re.search(r'\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b', date_node.text(), re.I)
        if weekday and show_date.strftime('%a').lower() != weekday[1].lower(): continue
        if not today <= show_date <= end: continue
        venue = venue_node.text()
        vid = venue_id_for(venue)
        if vid is None: continue
        title = ' '.join(title_node.text().split()); url = title_node.attrs['href']
        if re.search(r'\bcancell?ed\b',n.text(),re.I):continue
        if re.search(r'\bmarket\b|\btrivia\b|\bopen mic\b|\bthe moth\b|\bburlesque\b|\byoga\b|\bcraft\b', title, re.I): continue
        tm = re.search(r'Show:\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)', n.text(), re.I)
        # Keep unknown time explicit instead of inventing a showtime.
        start = show_date.isoformat()
        if tm:
            hour = int(tm[1]) % 12 + (12 if tm[3].lower() == 'pm' else 0)
            start += f' {hour:02d}:{int(tm[2] or 0):02d}:00'
        sub = next((x for x in nodes if x.attrs.get('id') == 'evSubHead'), None)
        billing_title = title
        if title.startswith('The Midnight:'): billing_title = 'The Midnight'
        if title.startswith('PUP:'): billing_title = 'PUP'
        if title.startswith('THE RESIDENTS –'): billing_title = 'The Residents'
        if title.startswith('Bitch Cabal feat.'): billing_title = 'Wednesday & Mannequin Pussy'
        performers = parse_performers(billing_title)
        if sub:
            labels = [x.text() for x in sub.walk() if x.tag == 'a'] or [sub.text()]
            for label in labels:
                for name in re.split(r'\s*\+\s*|\s*[\r\n]+\s*', label):
                    name = name.strip()
                    if not name or re.search(r'at hellbender|thompson st', name, re.I): continue
                    if normalize(name) not in {normalize(a['name']) for a in performers}:
                        performers.append({'name':name,'role':'support','confidence':1.0,'note':'Explicit official calendar support billing.'})
        ticket = next((x.attrs.get('href') for x in nodes if x.tag == 'a' and 'etix.com/ticket/' in x.attrs.get('href','')), None)
        events[url] = dict(source_key=source_name+':'+url, source_name=source_name, source_event_id=url,
            source_url=url, official_event_url=url, venue_id=vid, venue_as_reported=venue,
            title=title, performance_start=start, timezone='America/New_York', ticket_url=ticket,
            date_status='venue_confirmed', date_note='Date and venue read directly from official calendar.',
            artist_spotify_links={}, performers=performers)
    if not events:
        raise ValueError('Official calendar returned no parseable concerts; retain prior data and inspect source.')
    return sorted(events.values(), key=lambda e:e['performance_start'])

def fetch_official_events(days=None):
    r = requests.get('https://theorangepeel.net/events/', headers={'User-Agent':'Mozilla/5.0'}, timeout=30)
    r.raise_for_status()
    return parse_calendar(r.text, days=days)

def _event(source,url,title,start,venue,performers,ticket=None):
    return dict(source_key=source+':'+url,source_name=source,source_event_id=url,
        source_url=url,official_event_url=url,venue_id=venue_id_for(venue),venue_as_reported=venue,
        title=title,performance_start=start,timezone='America/New_York',ticket_url=ticket,
        date_status='venue_confirmed' if source.endswith('Official') else 'source_listed',
        date_note='Read from '+source+'.',artist_spotify_links={},performers=performers)

def parse_structured_events(html,source,today=None,days=None):
    """Public schema.org listings on the linked DICE calendar and Songkick."""
    today=today or date.today();end=(today+timedelta(days=days)) if days is not None else date.max
    p=Tree();p.feed(html);out={}
    def visit(obj):
        if isinstance(obj,list):
            for entry in obj:visit(entry)
        elif isinstance(obj,dict):
            if obj.get('@type') in ('MusicEvent','Event') and obj.get('startDate'):
                start=obj['startDate'];location=obj.get('location',{})
                venue=location.get('name','');vid=venue_id_for(venue)
                if vid=='sierra-nevada' and location.get('address',{}).get('addressLocality')!='Mills River':return
                if not vid or not today<=date.fromisoformat(start[:10])<=end:return
                if 'Cancelled' in obj.get('eventStatus',''):return
                title=obj['name'].split(' @ ')[0];url=obj['url'].split('?')[0]
                bill=obj.get('performer',[])
                if isinstance(bill,dict):bill=[bill]
                # Structured Songkick order is the headline act followed by support.
                performers=[dict(name=b['name'],role='headliner' if i==0 else 'support',confidence=1,note='Source lineup order.') for i,b in enumerate(bill)] or parse_performers(title)
                out[url]=_event(source,url,title,datetime.fromisoformat(start).strftime('%Y-%m-%d %H:%M:%S'),venue,performers,url)
            for key,value in obj.items():
                if key in ('event','@graph','itemListElement','item'):visit(value)
    for n in p.root.walk():
        if n.tag=='script' and n.attrs.get('type')=='application/ld+json':
            try:visit(json.loads(n.text()))
            except (ValueError,KeyError,TypeError):continue
    if not out:raise ValueError(source+' returned no parseable upcoming events.')
    return list(out.values())

def parse_harrah(html,today=None,days=None):
    today=today or date.today();end=(today+timedelta(days=days)) if days is not None else date.max;p=Tree();p.feed(html);out={}
    for n in p.root.walk():
        if not n.has('event-wrap_feed'):continue
        nodes=list(n.walk());heading=next((x for x in nodes if x.tag=='h3'),None)
        dn=next((x for x in nodes if x.has('event-date')),None);vn=next((x for x in nodes if x.has('event-venue')),None)
        if not heading or not dn or not vn:continue
        anchor=next((x for x in heading.walk() if x.tag=='a'),None)
        if not anchor:continue
        title=heading.text();url=anchor.attrs['href']
        if re.search(r'cancel|october skate party|roller derby|craft fair|justice forum|dance competition|championship|basketball|wrestling|expo|dance theatre|ballet|nutcracker',title,re.I) and not re.search(r'benefit show|music competition',title,re.I):continue
        raw=re.search(r'([A-Za-z]{3})\s+(\d{1,2})',' '.join(dn.text().split()))
        if not raw:continue
        ym=re.search(r'/events/(20\d\d)-',url);year=int(ym[1]) if ym else today.year
        day=datetime.strptime(f'{year} {raw[1]} {raw[2]}','%Y %b %d').date()
        if not ym and day.month<today.month:day=day.replace(year=today.year+1)
        if not today<=day<=end:continue
        venue=vn.text();vid=venue_id_for(venue)
        if not vid:continue
        billing=re.split(r'\s*[–:]\s*',title)[0]
        billing=re.sub(r'\s+Play Grateful Dead.*','',billing,flags=re.I)
        if billing=='JJ Grey & Mofro':performers=[dict(name=billing,role='headliner',confidence=1)]
        else:performers=parse_performers(billing)
        out[url]=_event('HarrahOfficial',url,title,day.isoformat(),venue,performers,url)
    if not out:raise ValueError('Harrah calendar returned no concerts.')
    return list(out.values())

CALENDARS=[
 ('OrangePeelOfficial','https://theorangepeel.net/events/','rhp'),
 ('MusicHallOfficial','https://ashevillemusichall.com/','rhp'),
 ('GreyEagleOfficial','https://www.thegreyeagle.com/calendar/','rhp'),
 ('HarrahOfficial','https://www.harrahscherokeecenterasheville.com/events-tickets/','harrah'),
 ('EulogyOfficial','https://dice.fm/venue/eulogy-7bd7?lng=en-US','structured'),
 ('SongkickPublic','https://www.songkick.com/metro-areas/86726-us-mills-river','structured'),
 ('SongkickOrange','https://www.songkick.com/venues/289-orange-peel/calendar','structured'),
 ('SongkickGrey','https://www.songkick.com/venues/39035-grey-eagle/calendar','structured'),
 ('SongkickAMH','https://www.songkick.com/venues/107138-asheville-music-hall/calendar','structured'),
 ('SongkickEulogy','https://www.songkick.com/venues/4519500-eulogy/calendar','structured'),
]
def fetch_all_calendars(days=None):
    from concurrent.futures import ThreadPoolExecutor
    def fetch(spec):
        source,url,kind=spec
        try:
            r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=30);r.raise_for_status()
            if kind=='rhp':events=parse_calendar(r.text,days=days,source_name=source)
            elif kind=='harrah':events=parse_harrah(r.text,days=days)
            else:events=parse_structured_events(r.text,source,days=days)
            if source=='SongkickPublic':events=[e for e in events if e['venue_id']=='sierra-nevada']
            return events,None
        except (requests.RequestException,ValueError) as error:return [],source+': '+str(error)
    events=[];errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for listings,error in pool.map(fetch,CALENDARS):
            events.extend(listings)
            if error:errors.append(error)
    return events,errors
