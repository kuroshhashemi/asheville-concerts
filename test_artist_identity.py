import unittest,tempfile
from pathlib import Path
from concert_discovery.storage import initialize,connect,upsert_artist
from concert_discovery.artist_identity import reconcile
class IdentityTests(unittest.TestCase):
 def test_future_typography_reuses_identity_and_preserves_profile(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'db';initialize(db)
   with connect(db) as c:
    one=upsert_artist(c,"Yo Mama’s Band",'A'*22)
    two=upsert_artist(c,"Yo Mama's Band")
    self.assertEqual(one,two)
    self.assertEqual(c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(one,)).fetchone()[0],'A'*22)
 def test_merge_keeps_history_and_conflicting_profiles_remain_separate(self):
  with tempfile.TemporaryDirectory() as td:
   db=Path(td)/'db';initialize(db)
   with connect(db) as c:
    a=upsert_artist(c,'Example’s Band','A'*22)
    c.execute('INSERT INTO artists SELECT ?,?,NULL,NULL,match_status,match_confidence,match_reason,updated_at FROM artists WHERE artist_id=?',('duplicate',"Example's Band",a))
    c.execute('CREATE TABLE history(snapshot_id INTEGER PRIMARY KEY,artist_id TEXT,value INTEGER)')
    c.execute('INSERT INTO history VALUES(1,?,42)',('duplicate',))
   reconcile(db)
   with connect(db) as c:self.assertEqual(tuple(c.execute('SELECT artist_id,value FROM history').fetchone()),(a,42))
   with connect(db) as c:
    c.execute('INSERT INTO artists SELECT ?,?, ?,?,match_status,match_confidence,match_reason,updated_at FROM artists WHERE artist_id=?',('conflict',"Example's Band",'B'*22,'https://open.spotify.com/artist/'+'B'*22,a))
   self.assertEqual(len(reconcile(db)['conflicts']),1)
