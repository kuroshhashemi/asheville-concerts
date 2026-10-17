"""Bounded hosted smoke test. No city feeds, emails, checkout or bulk backfill."""
import json,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch
from concert_discovery.storage import DATABASE_PATH,initialize
from concert_discovery.discovery import get_shows
from concert_discovery import brightdata_prices,ticketmaster_prices


def main():
    initialize();shows=get_shows();out={}
    etix=next((s for s in shows if '/ticket/p/61271182/' in (s.get('ticket_url') or '')),None)
    tm=next((s for s in shows if '2D006537C59525AF' in (s.get('ticket_url') or '')),None)
    if not etix or not tm:raise RuntimeError('Known validation samples missing; no requests made')
    with tempfile.TemporaryDirectory() as tmp:
        db=Path(tmp)/'sample.sqlite3'
        with sqlite3.connect(DATABASE_PATH) as source,sqlite3.connect(db) as dest:source.backup(dest)
        with sqlite3.connect(db) as c:
            for table in ('brightdata_price_checks','ticketmaster_price_checks'):
                if c.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():c.execute('DELETE FROM '+table)
        reserve=brightdata_prices.reserve
        with patch.object(brightdata_prices,'load',return_value={}),patch.object(brightdata_prices,'reserve',side_effect=lambda _:reserve(DATABASE_PATH)):
            out['web_unlocker']=brightdata_prices.refresh(db,limit=1,shows=[etix])
        out['ticketmaster']=ticketmaster_prices.refresh(db,limit=1,shows=[tm])
    print(json.dumps(out,indent=2),flush=True)
    Path('pricing-validation.json').write_text(json.dumps(out,indent=2))
    if out['web_unlocker'].get('brightdata_prices_saved')!=1 or out['ticketmaster'].get('ticketmaster_prices_saved')!=1:
        raise RuntimeError('Hosted pricing smoke test did not pass; inspect sanitized results')

if __name__=='__main__':main()
