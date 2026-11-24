import unittest,tempfile,json
from pathlib import Path
from concert_discovery.storage import initialize,connect,upsert_show
from concert_discovery.web_snapshot import export
class SnapshotTests(unittest.TestCase):
 def test_snapshot_is_public_deterministic_and_retains_show_identity(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'db';initialize(db)
   with connect(db) as c:
    sid=upsert_show(c,dict(source_key='OrangePeelOfficial:x',source_name='OrangePeelOfficial',source_event_id='x',source_url='https://example.com/x',venue_id='orange-peel',venue_as_reported='Orange Peel',title='Example Band',performance_start='2099-12-01 20:00:00',ticket_url='https://example.com/ticket',date_status='venue_confirmed',date_note='',performers=[{'name':'Example Band','role':'headliner','confidence':1}],artist_spotify_links={}))
    c.execute('INSERT INTO user_show_decisions VALUES(?,?,?,?)',('private-person@example.com',sid,'interested','2099-01-01'))
   db.with_name('freshness.json').write_text(json.dumps({'refreshed_at':'2026-11-24T00:00:00+00:00'}))
   a=export(db);b=export(db)
   self.assertEqual(a['version'],b['version']);self.assertEqual(a['rows'][0]['show_id'],sid)
   self.assertEqual(a['rows'][0]['status'],'Unread');self.assertNotIn('private-person',json.dumps(a))
   self.assertEqual(a['updated_at'],'2026-11-24T00:00:00+00:00')
