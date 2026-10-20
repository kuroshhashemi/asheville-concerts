"""Scoped public evidence migration; preserves newer data and original show rows."""
import json
from pathlib import Path

def apply(c):
 version='metadata-evidence-2026-10-19-v1'
 c.execute('CREATE TABLE IF NOT EXISTS public_catalog_patches(version TEXT PRIMARY KEY)')
 if c.execute('SELECT 1 FROM public_catalog_patches WHERE version=?',(version,)).fetchone():return
 data=json.loads((Path(__file__).parent/'assets/metadata-evidence-2026-10-19.json').read_text())
 from concert_discovery.pastspot import schema as history_schema
 from concert_discovery.ticket_destinations import schema as link_schema
 from concert_discovery.reconciliation import schema as alias_schema,canonical
 from concert_discovery.storage import utc_now
 history_schema(c);link_schema(c);alias_schema(c)
 mapping={r['dedupe_key']:r['show_id'] for r in c.execute('SELECT show_id,dedupe_key FROM shows')}
 for table in ('official_ticket_links','ticket_availability','history_checks','listener_history'):
  for item in data[table]:
   row=dict(item);key=row.pop('_show_key',None)
   if key:
    if key not in mapping:continue
    row['show_id']=canonical(c,mapping[key])
   if table=='listener_history':
    old=c.execute('SELECT * FROM listener_history WHERE spotify_id=? AND observed_date=?',(row['spotify_id'],row['observed_date'])).fetchone();stamp='imported_at'
   else:
    field={'official_ticket_links':'show_id','ticket_availability':'source_key','history_checks':'spotify_id'}[table]
    old=c.execute('SELECT * FROM '+table+' WHERE '+field+'=?',(row[field],)).fetchone();stamp='observed_at' if table=='ticket_availability' else 'checked_at'
   if old and (old[stamp] or '')>(row[stamp] or ''):continue
   cols=list(row)
   c.execute('INSERT OR REPLACE INTO '+table+'('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[row[k] for k in cols])
   if table=='official_ticket_links':c.execute('UPDATE shows SET ticket_url=? WHERE show_id=?',(row['url'],row['show_id']))
 for pair in data['aliases']:
  if pair['alias'] not in mapping or pair['canonical'] not in mapping:continue
  alias=canonical(c,mapping[pair['alias']]);keep=canonical(c,mapping[pair['canonical']])
  if alias==keep:continue
  a=c.execute('SELECT venue_id,performance_start,ticket_url FROM shows WHERE show_id=?',(alias,)).fetchone()
  b=c.execute('SELECT venue_id,performance_start,ticket_url FROM shows WHERE show_id=?',(keep,)).fetchone()
  from concert_discovery.ticket_destinations import identity
  if a['venue_id']!=b['venue_id'] or a['performance_start'][:10]!=b['performance_start'][:10]:continue
  if not identity(a['ticket_url']) or identity(a['ticket_url'])!=identity(b['ticket_url']):continue
  c.execute('INSERT INTO show_aliases VALUES(?,?,?,?)',(alias,keep,'Official dated event pages verify shared provider event; conflicting aggregator times',utc_now()))
  for table in ('show_sources','ticket_availability','show_classifications','show_event_states'):
   if c.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():c.execute('UPDATE '+table+' SET show_id=? WHERE show_id=?',(keep,alias))
  for row in c.execute('SELECT * FROM user_show_decisions WHERE show_id=?',(alias,)).fetchall():
   c.execute('INSERT INTO user_show_decisions VALUES(?,?,?,?) ON CONFLICT(user_id,show_id) DO UPDATE SET decision=excluded.decision,updated_at=excluded.updated_at WHERE excluded.updated_at>user_show_decisions.updated_at',(row['user_id'],keep,row['decision'],row['updated_at']))
  if c.execute("SELECT 1 FROM sqlite_master WHERE name='show_discovery'").fetchone():
   rows=c.execute('SELECT * FROM show_discovery WHERE show_id IN (?,?) ORDER BY first_seen_at',(keep,alias)).fetchall()
   if rows:c.execute('INSERT OR REPLACE INTO show_discovery VALUES(?,?,?)',(keep,rows[0]['first_seen_at'],min(r['eligible'] for r in rows)))
 c.execute('INSERT INTO public_catalog_patches VALUES(?)',(version,))
