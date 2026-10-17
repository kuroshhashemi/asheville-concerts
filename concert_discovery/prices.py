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
    if price['min']==0 and price['max']==0:return 'Free'
    if price['min']==0:return 'Free+'
    return f'${lo:,}' + ('+' if variable else '')

def load():
    path=Path(__file__).parent/'assets/ticket-prices.json'
    return json.loads(path.read_text()) if path.exists() else {}

def for_show(show,prices):
    urls=[show.get('official_event_url'),show.get('ticket_url')]+[s['source_url'] for s in show.get('sources',[])]
    candidates=[prices[url_key(url)] for url in urls if url and url_key(url) in prices]
    return next((p for p in candidates if p.get('includes_fees') is True),next(iter(candidates),None))

def structured(data):
    """Only explicit USD ticket offers/ranges; never guess from unrelated page text."""
    if data.get('isAccessibleForFree') is True:return {'min':0,'max':0}
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
    # Etix uses AggregateOffer -> offers -> individual ticket tiers.
    def expand(items):
        result=[]
        for item in items:
            if not isinstance(item,dict):continue
            if __import__('re').search(r'\b(student|child|children|youth|junior)\b',item.get('name',''),__import__('re').I):continue
            result.append(item)
            nested=item.get('offers') or []
            result.extend(expand([nested] if isinstance(nested,dict) else nested))
        return result
    candidates=expand(candidates)
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
    if re.search(r'\b(?:this is a free event|free admission|admission is free|free karaoke)\b|(?:^|[\n.!])\s*free event\b',text,re.I):return {'min':0,'max':0}
    # Use this only on an individual event card, not a whole venue page.
    values=[float(x.replace(',','')) for x in re.findall(r'\$\s*([\d,]+(?:\.\d{1,2})?)',text)]
    return {'min':min(values),'max':max(values),'from_price':bool(re.search(r'\bfrom\s*\$',text,re.I))} if values else None

def save(event,price):
    if not price:return
    from datetime import datetime,timezone
    path=Path(__file__).parent/'assets/ticket-prices.json'
    import fcntl
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        cached=load()
        url=event.get('official_event_url') or event.get('source_url') or event.get('ticket_url')
        if not url:return
        observed=event.get('price_observed_at') or datetime.now(timezone.utc).isoformat()
        old=cached.get(url_key(url))
        if old and old.get('includes_fees') is True and price.get('includes_fees') is not True:
            from datetime import timedelta
            try:
                if datetime.fromisoformat(old['observed_at'])>=datetime.now(timezone.utc)-timedelta(days=7):return
            except (KeyError,ValueError):pass
        cached[url_key(url)]={**price,'source_url':url,'source':event.get('source_name','Structured event data'),'detail':'Advertised event price','checked_at':observed[:10],'observed_at':observed}
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
                # Several venue templates publish a zero offer as a placeholder.
                if price and (price['max']>0 or value.get('isAccessibleForFree') is True or advertised(value.get('description',''))=={'min':0,'max':0}):prices.append(price)
            if '@graph' in value:walk(value['@graph'])
            if 'mainEntity' in value:walk(value['mainEntity'])
    for payload in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',markup,re.I|re.S):
        try:walk(json.loads(payload))
        except (ValueError,TypeError):
            try:walk(json.loads(html.unescape(payload)))
            except (ValueError,TypeError):pass
    return prices[0] if len(prices)==1 else None

def from_ticket_markup(url, markup, *, selected_quantity=None):
    """Provider-scoped ticket prices, preferring displayed totals including fees.

    Never scrape dollar amounts from descriptions, merchandise or upsells.
    Works on ordinary responses and cached rendered pages; does not bypass
    provider challenges or cause any additional network calls.
    """
    import re
    from concert_discovery.official_calendar import Tree
    host=(urlsplit(url).hostname or '').removeprefix('www.')
    tree=Tree();tree.feed(markup);values=[]
    if host=='etix.com':
        if any(re.fullmatch(r'Free\s*(?:&|and)\s*Family Friendly[.!]?',n.text().strip(),re.I) for n in tree.root.walk()):return {'min':0,'max':0,'includes_fees':True}
        for node in tree.root.walk():
            if node.attrs.get('role')=='combobox':
                text=node.attrs.get('aria-label','')
                if re.search(r'\b(student|child|children|youth|two pack|2 pack|four pack|4 pack)\b',text,re.I):continue
                if 'Price:' in text:
                    values.extend(float(v.replace(',','')) for v in re.findall(r'\$([\d,]+(?:\.\d{1,2})?)',text.split('Price:',1)[1]))
        if not values:
            for node in tree.root.walk():
                if node.has('smoketest-total'):
                    match=re.search(r'Total per ticket[^:]*:\s*((?:From\s*)?\$[\d,.]+(?:\s*(?:to|-)\s*\$[\d,.]+)?)',node.text(),re.I)
                    if match:values.extend(float(v.replace(',','')) for v in re.findall(r'\$([\d,]+(?:\.\d{1,2})?)',match[1]))
        if not values:
            match=re.search(r'TICKET PRICES CURRENTLY AVAILABLE(.*?)TICKET SALE DATES',tree.root.text(),re.S)
            if match and not re.search(r'\b(student|child|children|youth)\b',match[1],re.I):
                values.extend(float(v.replace(',','')) for v in re.findall(r'\$([\d,]+(?:\.\d{1,2})?)',match[1]))
    elif host=='ticketmaster.com':
        region=next((n for n in tree.root.walk() if n.attrs.get('role')=='menu' and n.attrs.get('aria-label','').startswith('Ticket listings sorted by lowest price')),None)
        if region and 'Prices include fees (before taxes)' in tree.root.text() and (selected_quantity==1 or any(re.search(r'current quantity:\s*1 Ticket$',n.attrs.get('aria-label','') or n.text()) for n in tree.root.walk() if n.tag=='button')):
            resale=False
            for node in region.walk():
                if node.tag!='button':continue
                label=node.attrs.get('aria-label','') or node.text()
                if re.search(r'\b(student|child|youth|cardmember|companion)\b',label,re.I):continue
                if not re.search(r'Standard Admission|Verified Resale Ticket|Official Platinum',label):continue
                match=re.search(r'\$([\d,]+(?:\.\d{1,2})?)',label)
                if match:values.append(float(match[1].replace(',','')));resale=resale or 'Resale' in label
            if values:return {'min':min(values),'max':max(values),'from_price':True,'includes_fees':True,'before_tax':True,'resale_included':resale,'resale_only':resale and not any('Standard Admission' in (n.attrs.get('aria-label','') or n.text()) or 'Official Platinum' in (n.attrs.get('aria-label','') or n.text()) for n in region.walk() if n.tag=='button'),'quantity':1}
    elif host=='tixr.com':
        for node in tree.root.walk():
            if not node.has('ticket') or node.attrs.get('data-row-type')!='primary':continue
            if node.attrs.get('data-product-state')!='OPEN':continue
            info=next((n for n in node.walk() if n.has('info')),None)
            if info:
                match=re.search(r'\$([\d,]+(?:\.\d{1,2})?)',info.text())
                if match:values.append(float(match.group(1).replace(',','')))
    elif host in ('dice.fm','link.dice.fm'):
        # DICE's event-page price statement explicitly includes mandatory fees.
        visible=re.sub(r'\s+',' ',tree.root.text())
        match=re.search(r'(From\s+)?\$([\d,]+(?:\.\d{1,2})?)\s+The price you',visible,re.I)
        if match:
            value=float(match.group(2).replace(',',''))
            return {'min':value,'max':value,'from_price':bool(match.group(1)),'includes_fees':True}
    elif host=='eventbrite.com' or host.endswith('.eventbrite.com'):
        # Current-event price region, not recommended events or sponsor prices.
        region=next((n for n in tree.root.walk() if n.attrs.get('aria-label')=='Tickets price and event schedule'),None)
        if region:
            match=re.search(r'(From\s+)?\$([\d,]+(?:\.\d{1,2})?)',region.text(),re.I)
            if match:
                value=float(match[2].replace(',',''))
                return {'min':value,'max':value,'from_price':bool(match[1]),'includes_fees':True}
    elif host=='secured.brevardmusic.org':
        # The seat map's low figure can be a student rate, not an adult ticket.
        legend=next((n for n in tree.root.walk() if n.attrs.get('id')=='tn-syos-legend-container'),None)
        if legend:
            values=[float(v.replace(',','')) for v in re.findall(r'Adult\s*:?\s*\$([\d,]+(?:\.\d{1,2})?)',legend.text(),re.I)]
            if values:return {'min':min(values),'max':max(values),'from_price':True}
    elif host=='jambase.com':
        # Only the current show's masthead, never nearby free shows or signup CTAs.
        if any(n.tag=='h1' and re.search(r'\bFREE SHOW\b',n.text(),re.I) for n in tree.root.walk()):
            return {'min':0,'max':0}
    elif host=='harrahscherokeecenterasheville.com':
        # Multi-day events may charge on one day and be free on another.
        days=[re.search(r'^DATE\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),',n.text().strip(),re.I) for n in tree.root.walk() if n.tag=='p']
        day=next((m[1] for m in days if m),None)
        if day:
            for n in tree.root.walk():
                if n.tag!='p' or not re.match(r'^(?:AVAILABILITY|TICKET PRICES)\s',n.text().strip()):continue
                if re.search(r'\b'+day+r'\s+(?:is\s+)?free\b|\bfree\s+on\s+'+day+r'\b',n.text(),re.I):return {'min':0,'max':0,'includes_fees':True}
        for node in tree.root.walk():
            if node.tag=='p' and (node.has('event-subtitle') or node.text().strip().startswith('KNOW BEFORE YOU GO')):
                price=advertised(node.text())
                if price:return price
    elif host in ('wl.seetickets.us','wl.eventim.us'):
        def current_nodes(node):
            if node.attrs.get('id','').startswith('addtomyorder'):return
            yield node
            for child in node.children:
                if hasattr(child,'attrs'):yield from current_nodes(child)
        root=next((n for n in tree.root.walk() if n.attrs.get('id')=='eventview'),None)
        if root:
            for n in current_nodes(root):
                if n.tag!='li':continue
                selector=next((x for x in n.walk() if x.tag=='select' and x.attrs.get('id','').startswith('tt_')),None)
                if not selector or 'disabled' in selector.attrs:continue
                if re.search(r'\b(student|child|children|youth)\b',n.text(),re.I):continue
                amount=next((x for x in n.walk() if x.attrs.get('id','').startswith('subtotal_')),None)
                if amount:
                    match=re.search(r'\$([\d,]+(?:\.\d{1,2})?)',amount.text())
                    if match:values.append(float(match[1].replace(',','')))
    if values:return {'min':min(values),'max':max(values),'includes_fees':True}
    return from_markup(markup)

def save_sierra_card_prices(markup):
    import re
    from concert_discovery.official_calendar import Tree
    from urllib.parse import urljoin
    tree=Tree();tree.feed(markup);count=0
    for card in tree.root.walk():
        if not card.has('event-card'):continue
        free=next((n for n in card.walk() if n.has('free-tag')),None)
        link=next((n.attrs.get('href') for n in card.walk() if n.tag=='a' and '/event/' in n.attrs.get('href','')),None)
        if free and link and re.search(r'\bTHIS IS A FREE EVENT\b',free.text(),re.I):
            save({'source_url':urljoin('https://sierranevada.com',link),'source_name':'Sierra Mills River calendar free-admission label'},{'min':0,'max':0});count+=1
    return count
