import tempfile,unittest
from pathlib import Path
from datetime import date,timedelta
from concert_discovery.storage import initialize,connect,upsert_show
from concert_discovery.api_sources import event
from concert_discovery.calendar_presence import record_snapshot
class CalendarPresenceTests(unittest.TestCase):
 def test_partial_and_repeat_cannot_retire_and_reappearance_restores(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'c.sqlite3';initialize(db)
   day=(date.today()+timedelta(days=10)).isoformat()
   e=event('EulogyOfficial','https://example.com/one','Known Artist',day,'eulogy',[{'name':'Known Artist','role':'headliner','confidence':1}])
   old=event('CityFeed','https://example.com/old','Old Artist',day,'eulogy',[{'name':'Old Artist','role':'headliner','confidence':1}])
   with connect(db) as c:
    upsert_show(c,e);old_id=upsert_show(c,old)
   snap=dict(check_id='1',complete=False,venue_id='eulogy',source_url='https://example.com',event_keys=[e['source_key']])
   record_snapshot(snap,db)
   with connect(db) as c:self.assertEqual(c.execute('SELECT count(*) FROM calendar_presence').fetchone()[0],0)
   snap['complete']=True;record_snapshot(snap,db);record_snapshot(snap,db)
   with connect(db) as c:self.assertEqual(c.execute('SELECT misses FROM calendar_presence WHERE show_id=?',(old_id,)).fetchone()[0],1)
   snap['check_id']='2';record_snapshot(snap,db)
   with connect(db) as c:self.assertEqual(c.execute('SELECT misses FROM calendar_presence WHERE show_id=?',(old_id,)).fetchone()[0],2)
   snap.update(check_id='3',event_keys=[e['source_key'],old['source_key']]);record_snapshot(snap,db)
   with connect(db) as c:self.assertEqual(c.execute('SELECT misses FROM calendar_presence WHERE show_id=?',(old_id,)).fetchone()[0],0)
 def test_missing_event_keys_rejects_snapshot(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'c.sqlite3';initialize(db)
   with self.assertRaises(ValueError):record_snapshot(dict(check_id='bad',complete=True,venue_id='eulogy',source_url='x',event_keys=['not-saved']),db)

class IdentityRefreshRegressionTests(unittest.TestCase):
 def test_cleaner_lineup_preserves_verified_bill_identity(self):
  from concert_discovery.storage import upsert_artist
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'c.sqlite3';initialize(db)
   day=(date.today()+timedelta(days=10)).isoformat()
   title='Example Artist - The Tour'
   with connect(db) as c:
    aid=upsert_artist(c,title,'A'*22,'Source-provided profile')
    c.execute("UPDATE artists SET match_status='source_link' WHERE artist_id=?",(aid,))
    old=event('EulogyOfficial','https://example.com/event',title,day,'eulogy',[{'name':title,'role':'headliner','confidence':1}])
    sid=upsert_show(c,old)
    new=dict(old,performers=[{'name':'Example Artist','role':'headliner','confidence':1}])
    self.assertEqual(upsert_show(c,new),sid)
    self.assertEqual(c.execute('SELECT artist_id FROM show_artists WHERE show_id=?',(sid,)).fetchone()[0],aid)
    self.assertEqual(c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(aid,)).fetchone()[0],'A'*22)
