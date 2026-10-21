"""Growth requests use a shared cap plus the owner's verified unfunded account."""
import json,os
from pathlib import Path
from concert_discovery.api_sources import secret
from concert_discovery.brightdata_prices import reserve

POLICY=Path(__file__).parent/'assets/brightdata-free-only.json'

def reserve_growth(db_path):
    if os.environ.get('BRIGHTDATA_GROWTH_DISABLED')=='1':return False,'Growth fallback disabled'
    if not secret('BRIGHTDATA_API_KEY'):return False,'Bright Data credentials unavailable'
    try:policy=json.loads(POLICY.read_text())
    except (OSError,ValueError):return False,'Free-only account settings unverified'
    # Bright Data stops unfunded accounts at free-credit exhaustion. This is an
    # owner attestation, not API telemetry: reverify before funding or recharge.
    if policy.get('paid_balance')!=0 or policy.get('auto_recharge_off') is not True or not policy.get('owner_confirmed_at'):
        return False,'Free-only account settings unverified'
    if not reserve(db_path):return False,'Shared Bright Data request cap reached'
    return True,'Unfunded account hard stop confirmed; shared request reserved'
