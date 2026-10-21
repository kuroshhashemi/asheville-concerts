"""Bounded public Ticketmaster adult inventory prices; no account or paid API.

The website's FlatBuffers layout is undocumented. Unknown layouts, currencies,
version mismatches and restricted offers fail closed, preserving saved prices.
"""
import base64
from datetime import datetime, timedelta, timezone
import json
import re
import struct
import time
from urllib.parse import parse_qs, unquote, urlsplit

import requests
from concert_discovery.storage import DATABASE_PATH, connect, utc_now
from concert_discovery.prices import save

APP = 'PRD115_GEDP'
SOCKET = 'wss://marketplace.prod.pub-tmaws.io/avpp/v2/graphql?app=' + APP
QUERY = '''subscription AvailabilityChanged($eventId: String!) {
 availability(eventId: $eventId) { buffer __typename }
}'''


def event_id(url):
    p = urlsplit(url or '')
    host = (p.hostname or '').lower()
    if host == 'ticketmaster.evyy.net':
        return event_id(parse_qs(p.query).get('u', [''])[0])
    if host not in ('ticketmaster.com', 'www.ticketmaster.com'):
        return None
    m = re.search(r'/event/([0-9A-Fa-f]{16})(?:/|$)', unquote(p.path))
    return m[1].upper() if m else None


class Buffer:
    def __init__(self, data):
        if not 8 <= len(data) <= 2_000_000:
            raise ValueError('Unsupported inventory buffer')
        self.data = data
        self.root = self.uint(0)

    def read(self, fmt, pos):
        if pos < 0 or pos + struct.calcsize(fmt) > len(self.data):
            raise ValueError('Invalid inventory offset')
        return struct.unpack_from(fmt, self.data, pos)[0]

    def uint(self, pos): return self.read('<I', pos)
    def integer(self, pos): return self.read('<i', pos)

    def field(self, pos, index):
        if not pos: raise ValueError('Missing inventory table')
        vtable = pos - self.integer(pos)
        offset = 4 + index * 2
        size = self.read('<H', vtable)
        member = self.read('<H', vtable + offset) if offset < size else 0
        return pos + member if member else 0

    def obj(self, pos, index):
        member = self.field(pos, index)
        return member + self.uint(member) if member else 0

    def text(self, pos, index):
        start = self.obj(pos, index)
        if not start: return None
        size = self.uint(start)
        if size > 100_000 or start + 4 + size > len(self.data):
            raise ValueError('Invalid inventory string')
        return self.data[start + 4:start + 4 + size].decode('utf-8')

    def val(self, pos, index):
        member = self.field(pos, index)
        return self.integer(member) if member else 0

    def flag(self, pos, index):
        member = self.field(pos, index)
        return bool(self.read('<B', member)) if member else False

    def vector(self, pos, index, objects=False):
        start = self.obj(pos, index)
        if not start: return []
        size = self.uint(start)
        if size > 100_000 or start + 4 + 4 * size > len(self.data):
            raise ValueError('Invalid inventory vector')
        return [start + 4 + 4 * n + self.uint(start + 4 + 4 * n)
                if objects else self.integer(start + 4 + 4 * n) for n in range(size)]


def versions(availability, eid):
    a = Buffer(availability)
    if a.text(a.root, 6) != eid: raise ValueError('Wrong event identity')
    manifest, pricing = a.text(a.root, 8), a.text(a.root, 9)
    if not manifest or not pricing: raise ValueError('Missing inventory version')
    return manifest, pricing


def decode(event, availability, eid):
    manifest, version = versions(availability, eid)
    a, e = Buffer(availability), Buffer(event)
    pricing, seats = e.obj(e.root, 0), e.obj(e.root, 1)
    if e.text(pricing, 5) != version or e.text(seats, 3) != manifest:
        raise ValueError('Inventory versions differ')
    if e.text(pricing, 6) != 'USD': raise ValueError('Unsupported currency')
    available = set()
    for section in a.vector(a.obj(a.root, 11), 3, True):
        for status in a.vector(section, 0, True):
            if a.text(status, 0) == 'OPEN':
                available.update(a.val(c, 0) for c in a.vector(status, 1, True) if a.val(c, 1) > 0)
    keys, prices = e.obj(pricing, 9), e.obj(pricing, 10)
    pids, oids = e.vector(keys, 3), e.vector(keys, 2)
    display, facility, service = [e.vector(prices, n) for n in (1, 3, 4)]
    offers = {e.val(o, 3): o for o in e.vector(pricing, 8, True)}
    totals = []
    for key in available:
        if not 0 <= key < min(len(pids), len(oids)): raise ValueError('Unknown price key')
        pid, offer = pids[key], offers.get(oids[key])
        if offer is None: continue
        # Conservative: no student/child/member/presale/platinum guesses.
        code = (e.text(offer, 5) or '').upper()
        label = re.sub(r'[^A-Z]', '', (e.text(offer, 6) or '').upper())
        if re.search(r'STUDENT|CHILD|YOUTH|SENIOR|MEMBER|COMPANION', code + ' ' + label): continue
        public_labels = {'STANDARDADMISSION','GENERALADMISSION','ADULT','OFFICIALPLATINUM','GAFLOOR','GAPIT','GALAWN','GABOWL','GASTANDING'}
        if label not in public_labels and code not in {'ADULT','STANDARD','REGULAR','GA'}:
            continue
        enabled = e.obj(offer, 14)
        if (e.flag(offer, 1) or e.flag(offer, 18) or e.vector(offer, 10)
                or (enabled and not e.flag(enabled, 0))):
            continue
        if pid < 0 or pid >= len(display): raise ValueError('Unknown price index')
        parts = [display[pid]]
        for included, values in ((e.flag(pricing, 0), facility), (e.flag(pricing, 1), service)):
            if not included:
                if pid >= len(values): raise ValueError('Missing mandatory fee')
                parts.append(values[pid])
        if any(v < 0 for v in parts): continue
        total = sum(parts)
        if 0 <= total < 10_000_000: totals.append(total / 100)
    if not totals: return None
    return {'min': min(totals), 'max': max(totals), 'from_price': len(set(totals)) > 1,
            'includes_fees': True, 'before_tax': not e.flag(pricing, 1), 'currency': 'USD', 'quantity': 1}


def fetch(eid):
    import websocket
    deadline = time.monotonic() + 15
    ws = websocket.create_connection(SOCKET, subprotocols=['graphql-ws'], timeout=12,
                                     origin='https://www.ticketmaster.com')
    try:
        ws.send(json.dumps({'type': 'connection_init', 'payload': {}}))
        ws.send(json.dumps({'id': '1', 'type': 'start', 'payload': {
            'operationName': 'AvailabilityChanged', 'variables': {'eventId': eid}, 'query': QUERY}}))
        for _ in range(12):
            ws.settimeout(max(.1, deadline - time.monotonic()))
            message = json.loads(ws.recv())
            encoded = message.get('payload', {}).get('data', {}).get('availability', {}).get('buffer')
            if encoded:
                availability = base64.b64decode(encoded, validate=True)
                break
            if time.monotonic() >= deadline or message.get('type') in ('error', 'connection_error'):
                raise ValueError('Inventory unavailable')
        else: raise ValueError('No availability response')
    finally:
        ws.close()
    manifest, pricing = versions(availability, eid)
    response = requests.get('https://pubapi.ticketmaster.com/avsc/events/' + eid,
        params={'app': APP}, headers={'Accept': 'application/octet-stream',
        'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.ticketmaster.com/',
        'x-tm-manifest-version': manifest, 'x-tm-pricing-version': pricing}, timeout=15)
    response.raise_for_status()
    return decode(response.content, availability, eid)


def refresh(db_path=DATABASE_PATH, limit=12, shows=None, force=False, priority_ids=None):
    from concert_discovery.discovery import get_shows
    from datetime import date
    from concert_discovery.prices import load, for_show
    shows = get_shows(db_path) if shows is None else shows
    prices = load()
    shows = [s for s in shows if str(s.get('performance_start',''))[:10]>=date.today().isoformat()]
    shows = sorted(shows, key=lambda s: (s['show_id'] not in priority_ids if priority_ids else False,for_show(s, prices) is not None, s.get('performance_start', '')))
    groups = {}
    for show in shows:
        if show.get('on_sale_label'):continue
        urls = [show.get('ticket_url'), show.get('official_event_url')] + [s['source_url'] for s in show.get('sources', [])]
        ids = {event_id(u) for u in urls if event_id(u)}
        if len(ids) != 1: continue  # Never guess across a multi-date venue page.
        eid = ids.pop()
        groups.setdefault(eid, set()).update(u for u in urls if event_id(u) == eid)
    result = {'ticketmaster_price_events_checked': 0, 'ticketmaster_prices_saved': 0, 'ticketmaster_price_failures': 0}
    with connect(db_path) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS ticketmaster_price_checks(
            event_id TEXT PRIMARY KEY,checked_at TEXT,status TEXT,price_json TEXT,parser_revision INTEGER DEFAULT 0)''')
        if 'parser_revision' not in {r[1] for r in c.execute('PRAGMA table_info(ticketmaster_price_checks)')}:
            c.execute('ALTER TABLE ticketmaster_price_checks ADD COLUMN parser_revision INTEGER DEFAULT 0')
        cached = {r['event_id']: dict(r) for r in c.execute('SELECT * FROM ticketmaster_price_checks')}
    for eid, urls in groups.items():
        row = cached.get(eid)
        ttl = 1  # Refresh saved prices and unsuccessful checks daily.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl)).isoformat()
        if not force and row and row['checked_at'] >= cutoff and row['parser_revision']==2:
            price = json.loads(row['price_json']) if row['price_json'] else None
            observed = row['checked_at']
        else:
            if result['ticketmaster_price_events_checked'] >= max(0, limit): continue
            result['ticketmaster_price_events_checked'] += 1
            observed = utc_now()
            try:
                price = fetch(eid)
                status = 'priced' if price else 'no_supported_adult_offer'
            except Exception as error:
                kind=type(error).__name__
                http=getattr(error,'status_code',None) or getattr(getattr(error,'response',None),'status_code',None)
                result.setdefault('ticketmaster_error_types',[]).append(kind+(f' HTTP {http}' if http else ''))
                price = None
                status = 'unavailable'
                result['ticketmaster_price_failures'] += 1
            with connect(db_path) as c:
                c.execute('INSERT OR REPLACE INTO ticketmaster_price_checks VALUES(?,?,?,?,?)',
                          (eid, observed, status, json.dumps(price) if price else None, 2))
            if result['ticketmaster_price_failures'] >= 3: break
        if price:
            for url in urls:
                save({'source_url': url, 'source_name': 'Ticketmaster public adult inventory, fees included',
                      'price_observed_at': observed}, price)
            result['ticketmaster_prices_saved'] += 1
    return result
