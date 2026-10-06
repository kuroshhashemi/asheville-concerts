"""Explicit ticket availability only; missing evidence remains unknown."""
import re

def text_availability(text):
    if re.search(r"\bsold[\s-]*out\b", text, re.I): return 'sold_out'
    return None

def structured_availability(event):
    offers=event.get('offers',[])
    if isinstance(offers,dict):offers=[offers]
    states=[o.get('availability','').rstrip('/').rsplit('/',1)[-1] for o in offers if isinstance(o,dict)]
    if states and all(s=='SoldOut' for s in states):return 'sold_out'
    if 'InStock' in states or 'LimitedAvailability' in states:return 'available'
    return None
