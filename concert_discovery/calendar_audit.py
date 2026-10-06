"""Completeness-gated snapshots for supported official calendars."""
import uuid,re
from urllib.parse import urljoin,urlparse
from concert_discovery.official_calendar import Tree

def collect_pages(url,load,parse,max_pages=10):
    rows={};seen=set();pages=0
    while url:
        if url in seen or pages>=max_pages:raise ValueError('Calendar pagination incomplete')
        seen.add(url);markup=load(url);tree=Tree();tree.feed(markup)
        parsed=parse(markup)
        # All dated event cards must have survived parsing, apart from intentional categories.
        for n in tree.root.walk():
            if n.has('eventWrapper'):
                title=next((x for x in n.walk() if x.attrs.get('id')=='eventTitle'),None)
                if title and title.attrs.get('href') not in {r['source_url'] for r in parsed}:
                    if not re.search(r'cancel|market|trivia|open mic|the moth|burlesque|yoga|craft',title.text(),re.I):
                        raise ValueError('Unparsed calendar card; retirement disabled')
        for row in parsed:rows[row['source_key']]=row
        pages+=1
        # RHP's actual pagination controls, not unrelated WordPress rel=next metadata.
        controls=[n for n in tree.root.walk() if n.has('rhp-pagination')]
        links=[n for root in controls for n in root.walk() if n.tag=='a' and ('next' in (n.text()+' '+n.attrs.get('class','')).lower())]
        if any(re.search('load more|show more',n.text(),re.I) for n in tree.root.walk() if n.tag=='button'):raise ValueError('Uncollected dynamic calendar pages')
        next_url=urljoin(url,links[0].attrs.get('href','')) if links else None
        if next_url and urlparse(next_url).netloc!=urlparse(url).netloc:raise ValueError('Unexpected pagination destination')
        url=next_url
    if not rows:raise ValueError('Empty calendar; retirement disabled')
    return list(rows.values()),pages

def snapshots(rows,url,pages):
    return [dict(check_id=str(uuid.uuid4()),venue_id=vid,complete=True,event_keys=[r['source_key'] for r in rows if r['venue_id']==vid],source_url=url,pages=pages)
            for vid in sorted({r['venue_id'] for r in rows})]
