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

def structured(data):
    """Only explicit USD ticket offers/ranges; never guess from unrelated page text."""
    values=[];variable=False
    def number(value):
        try:
            value=float(value)
            return value if 0<=value<100000 else None
        except (TypeError,ValueError):return None
    candidates=list(data.get('priceRanges') or [])
    offers=data.get('offers') or []
    if isinstance(offers,dict):offers=[offers]
    candidates+=offers
    details=data.get('cost_details') or {}
    if details.get('currency_code')=='USD':
        candidates += [{'price':v,'priceCurrency':'USD'} for v in details.get('values',[])]
    for item in candidates:
        if not isinstance(item,dict) or (item.get('currency') or item.get('priceCurrency'))!='USD':continue
        for k in ('min','max','price','lowPrice','highPrice'):
            n=number(item.get(k))
            if n is not None:values.append(n)
        variable=variable or 'lowPrice' in item or item.get('@type')=='AggregateOffer'
    return {'min':min(values),'max':max(values),'from_price':variable} if values else None

def advertised(text):
    import re
    if re.search(r'\b(?:this is a free event|free admission|admission is free)\b',text,re.I):return {'min':0,'max':0}
    # Use this only on an individual event card, not a whole venue page.
    values=[float(x.replace(',','')) for x in re.findall(r'\$\s*([\d,]+(?:\.\d{1,2})?)',text)]
    return {'min':min(values),'max':max(values),'from_price':bool(re.search(r'\bfrom\s*\$',text,re.I))} if values else None

def save(event,price):
    if not price:return
    from datetime import datetime,timezone
    path=Path(__file__).parent/'assets/ticket-prices.json'
    cached=load()
    url=event.get('official_event_url') or event.get('source_url') or event.get('ticket_url')
    if not url:return
    cached[url_key(url)]={**price,'source_url':url,'source':event.get('source_name','Structured event data'),'detail':'Advertised event price','checked_at':datetime.now(timezone.utc).date().isoformat(),'observed_at':datetime.now(timezone.utc).isoformat()}
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(cached,indent=2));temporary.replace(path)

def from_markup(markup):
    import re,html
    prices=[]
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            types=value.get('@type',[]);types=[types] if isinstance(types,str) else types
            if any(t in ('Event','MusicEvent','ComedyEvent','TheaterEvent','DanceEvent','SportsEvent') for t in types):
                price=structured(value)
                if price:prices.append(price)
            if '@graph' in value:walk(value['@graph'])
    for payload in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',markup,re.I|re.S):
        try:walk(json.loads(html.unescape(payload)))
        except (ValueError,TypeError):pass
    return prices[0] if len(prices)==1 else None
