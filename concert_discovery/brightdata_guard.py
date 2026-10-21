"""Free-only growth gate. Unknown account allowance never authorizes a request."""
import requests
from concert_discovery.api_sources import secret

def reserve_growth(db_path):
    key=secret('BRIGHTDATA_API_KEY')
    if not key:return False,'Bright Data credentials unavailable'
    try:
        response=requests.get('https://api.brightdata.com/customer/balance',headers={'Authorization':'Bearer '+key},timeout=15)
        if not response.ok:return False,'Free allowance verification failed (HTTP '+str(response.status_code)+')'
        data=response.json()
    except (requests.RequestException,ValueError):return False,'Free allowance verification unavailable'
    # Do not mistake ordinary wallet dollars or promotional paid balance for free credits.
    # No currently verified API schema exposes this guarantee. Keep fail-closed until
    # a documented free-only authorization is available; balance alone is insufficient.
    return False,'Balance API does not verify a free-only spending guarantee'
