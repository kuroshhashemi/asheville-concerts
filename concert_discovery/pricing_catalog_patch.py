"""Apply saved public ticket evidence without replacing a newer collected catalog."""
import json
from pathlib import Path


def apply(connection):
    path=Path(__file__).parent/'assets/pricing-evidence-2026-10-17.json'
    if not path.exists():return
    connection.execute('CREATE TABLE IF NOT EXISTS public_catalog_patches(version TEXT PRIMARY KEY)')
    version='pricing-evidence-2026-10-17'
    if connection.execute('SELECT 1 FROM public_catalog_patches WHERE version=?',(version,)).fetchone():return
    payload=json.loads(path.read_text())
    mapping={r['dedupe_key']:r['show_id'] for r in connection.execute('SELECT show_id,dedupe_key FROM shows')}
    for table in ('ticket_availability','ticket_sale_windows','official_ticket_links','provider_ticket_links'):
        item=payload[table];connection.execute(item['schema'])
        for row in item['rows']:
            r=dict(row);show_key=r.pop('_show_key',None)
            if show_key:
                if show_key not in mapping:continue
                r['show_id']=mapping[show_key]
            key='source_key' if table=='ticket_availability' else 'event_id' if table=='provider_ticket_links' else 'show_id'
            stamp='observed_at' if 'observed_at' in r else 'checked_at'
            old=connection.execute('SELECT * FROM '+table+' WHERE '+key+'=?',(r[key],)).fetchone()
            if old and (old[stamp] or '')>(r[stamp] or ''):continue
            cols=list(r)
            connection.execute('INSERT OR REPLACE INTO '+table+'('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[r[k] for k in cols])
            if table=='official_ticket_links':connection.execute('UPDATE shows SET ticket_url=? WHERE show_id=?',(r['url'],r['show_id']))
    connection.execute('INSERT INTO public_catalog_patches VALUES(?)',(version,))
