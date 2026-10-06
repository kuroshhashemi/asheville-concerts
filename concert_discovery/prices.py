"""Cached advertised prices; unknown values are never inferred as free."""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit, unquote

def url_key(url):
    p=urlsplit(url or '')
    return p.netloc.lower().removeprefix('www.')+unquote(p.path).rstrip('/')

def rounded(value):
    return int(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def label(price):
    if not price:return ''
    lo,hi=rounded(price['min']),rounded(price['max'])
    variable=price['max']>price['min'] or price.get('from_price',False)
    return f'${lo:,}' + ('+' if variable else '')

def load():
    path=Path(__file__).parent/'assets/ticket-prices.json'
    return json.loads(path.read_text()) if path.exists() else {}

def for_show(show,prices):
    urls=[show.get('official_event_url'),show.get('ticket_url')]+[s['source_url'] for s in show.get('sources',[])]
    return next((prices[url_key(url)] for url in urls if url and url_key(url) in prices),None)
