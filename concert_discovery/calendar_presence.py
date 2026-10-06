"""Retire display entries after two complete authoritative-calendar absences."""
from datetime import date
from concert_discovery.storage import connect,utc_now

def record_snapshot(snapshot,db_path=None):
 if not snapshot.get('complete'):return {'retired':0}
 with connect(db_path) as c:
  if c.execute('SELECT 1 FROM calendar_checks WHERE check_id=?',(snapshot['check_id'],)).fetchone():return {'retired':0}
  from concert_discovery.reconciliation import canonical,schema as alias_schema
  alias_schema(c)
  keys=snapshot['event_keys']
  if not keys:raise ValueError('Empty calendar cannot retire shows automatically.')
  present=set()
  for key in keys:
   row=c.execute('SELECT show_id FROM show_sources WHERE source_key=?',(key,)).fetchone()
   if not row:raise ValueError('Calendar event must be saved before recording completeness.')
   present.add(canonical(c,row[0]))
  c.execute('INSERT INTO calendar_checks VALUES(?,?,?,?)',(snapshot['check_id'],snapshot['venue_id'],snapshot['source_url'],utc_now()))
  for row in c.execute('SELECT show_id FROM shows WHERE venue_id=? AND substr(performance_start,1,10)>=?',(snapshot['venue_id'],date.today().isoformat())).fetchall():
   sid=row[0]
   if canonical(c,sid)!=sid:continue
   c.execute('''INSERT INTO calendar_presence VALUES(?,?,?) ON CONFLICT(show_id) DO UPDATE SET
       misses=CASE WHEN excluded.misses=0 THEN 0 ELSE calendar_presence.misses+1 END,
       checked_at=excluded.checked_at''',(sid,0 if sid in present else 1,utc_now()))
  return {'retired':c.execute('SELECT count(*) FROM calendar_presence p JOIN shows s USING(show_id) WHERE venue_id=? AND misses>=2',(snapshot['venue_id'],)).fetchone()[0]}
