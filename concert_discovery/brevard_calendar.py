"""Brevard Music Center's public calendar, with completeness-gated pagination."""
from datetime import date, datetime
import re
from urllib.parse import urljoin, urlparse
import requests
from concert_discovery.official_calendar import Tree, _event
from concert_discovery.event_sources import parse_performers
from concert_discovery.availability import text_availability

URL = 'https://www.brevardmusic.org/events/'

def parse(html, today=None):
    today = today or date.today()
    tree = Tree(); tree.feed(html)
    rows = []
    for card in tree.root.walk():
        if card.tag != 'article' or not card.has('type-event'): continue
        nodes = list(card.walk())
        heading = next((n for n in nodes if n.tag == 'h1'), None)
        link = next((n for n in heading.walk() if n.tag == 'a'), None) if heading else None
        timestamp = next((n.text() for n in nodes if n.has('date') and re.search(r'\b20\d\d\b',n.text()) and ',' in n.text()), None)
        if not link or not timestamp: raise ValueError('Unparsed Brevard card; retirement disabled')
        try:
            start = datetime.strptime(' '.join(timestamp.split()), '%A, %B %d, %Y, %I:%M %p')
        except ValueError: raise ValueError('Unknown Brevard date format; retirement disabled') from None
        if start.date() < today: continue
        title = link.text()
        # Explicit presentation prefixes distinguish the act from the show title.
        billing = re.split(r'\s+with\s+', title, flags=re.I)[-1]
        billing = re.sub(r'\s+in Recital$', '', billing, flags=re.I)
        performers = [] if re.search(r"messiah", billing, re.I) else parse_performers(billing)
        ticket = next((n.attrs.get('href') for n in nodes if n.tag == 'a' and n.has('tickets')), None)
        row = _event('BrevardOfficial', link.attrs['href'], title, start.strftime('%Y-%m-%d %H:%M:%S'), 'Brevard Music Center', performers, ticket or link.attrs['href'])
        row['category_text'] = ' '.join(n.text() for n in nodes if n.has('category'))
        row['ticket_availability'] = text_availability(' '.join(n.text() for n in nodes if n.has('links')))
        row['event_status'] = 'cancelled' if re.search(r'\bcancell?ed\b',title,re.I) else 'scheduled'
        rows.append(row)
    next_links = [n.attrs.get('href') for n in tree.root.walk() if n.tag == 'a' and (n.attrs.get('rel') == 'next' or (n.has('next') and n.has('page-numbers')))]
    if any(re.search(r'load more|show more',n.text(),re.I) for n in tree.root.walk() if n.tag == 'button'):
        raise ValueError('Uncollected Brevard dynamic pages; retirement disabled')
    if not rows: raise ValueError('Empty Brevard calendar; prior data retained')
    return rows, next_links[0] if next_links else None

def fetch_brevard(load=None):
    if load is None:
        def load(url):
            r=requests.get(url,timeout=30); r.raise_for_status(); return r.text
    url=URL; seen=set(); rows={}
    while url:
        if url in seen or len(seen)>=10: raise ValueError('Incomplete Brevard pagination')
        seen.add(url)
        events,next_url=parse(load(url))
        for row in events: rows[row['source_key']]=row
        url=urljoin(url,next_url) if next_url else None
        if url and urlparse(url).netloc != urlparse(URL).netloc: raise ValueError('Unexpected Brevard pagination host')
    from concert_discovery.calendar_audit import snapshots
    return list(rows.values()), snapshots(list(rows.values()), URL, len(seen))
