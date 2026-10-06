"""Reversible consolidation using the same identity rule as import and display."""
from concert_discovery.storage import connect,DATABASE_PATH,utc_now
from concert_discovery.reconciliation import catalog_rows,duplicate,is_official,schema

def cleanup_duplicates(db_path=DATABASE_PATH):
 with connect(db_path) as c:
  schema(c);rows=catalog_rows(c);kept=[];log=[]
  for drop in sorted(rows,key=lambda s:(not is_official(s),s['show_id'])):
   keep=next((k for k in kept if duplicate(k,drop,rows)),None)
   if keep is None:kept.append(drop);continue
   k,d=keep['show_id'],drop['show_id']
   # Keep original rows and personal decisions for recovery and account-key aliases.
   c.execute('INSERT INTO show_aliases VALUES(?,?,?,?)',(d,k,'Same room/date/bill with compatible performance time',utc_now()))
   for table in ('ticket_availability','show_sources','show_classifications','show_event_states'):
    if c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():c.execute('UPDATE '+table+' SET show_id=? WHERE show_id=?',(k,d))
   for decision in c.execute('SELECT * FROM user_show_decisions WHERE show_id=?',(d,)).fetchall():
    c.execute('INSERT INTO user_show_decisions VALUES(?,?,?,?) ON CONFLICT(user_id,show_id) DO UPDATE SET decision=excluded.decision,updated_at=excluded.updated_at WHERE excluded.updated_at>user_show_decisions.updated_at',(decision['user_id'],k,decision['decision'],decision['updated_at']))
   if c.execute("SELECT 1 FROM sqlite_master WHERE name='show_discovery'").fetchone():
    dates=c.execute('SELECT * FROM show_discovery WHERE show_id IN (?,?) ORDER BY first_seen_at',(k,d)).fetchall()
    if dates:c.execute('INSERT OR REPLACE INTO show_discovery VALUES(?,?,?)',(k,dates[0]['first_seen_at'],min(r['eligible'] for r in dates)))
   # Official billing remains authoritative; retain original alias lineup as evidence.
   if not is_official(keep):c.execute('INSERT OR IGNORE INTO show_artists SELECT ?,artist_id,billing_role,role_confidence,role_source,role_note FROM show_artists WHERE show_id=?',(k,d))
   log.append({'keep':k,'removed':d,'title':keep['title'],'date':keep['performance_start'][:10],'reason':'reversible duplicate alias'})
  return log
