import tempfile, unittest
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
from concert_discovery.storage import initialize,connect
from concert_discovery.api_sources import event
from concert_discovery.refresh import save_events
from concert_discovery.matching_queue import enqueue,run

class QueueTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.db=Path(self.temp.name)/'db.sqlite3';initialize(self.db)
  self.e=event('EulogyOfficial','https://example.com/show','Example',(date.today()+timedelta(days=10)).isoformat(),'eulogy',[{'name':'Example','role':'headliner','confidence':1}])
  save_events([self.e],self.db)
 def job(self):
  with connect(self.db) as c:return dict(c.execute('SELECT * FROM artist_matching_jobs').fetchone())
 def test_import_persists_pending_and_repeat_does_not_reset_retry(self):
  self.assertEqual(self.job()['state'],'pending')
  with connect(self.db) as c:c.execute("UPDATE artist_matching_jobs SET state='blocked',next_attempt_at='2099-01-01'")
  save_events([self.e],self.db)
  self.assertEqual(self.job()['next_attempt_at'],'2099-01-01')
 def test_blocked_attempt_is_retried_later_and_budget_preserves_pending(self):
  from concert_discovery.spotify_matching import SpotifyUnavailable
  with patch('concert_discovery.spotify_matching.SpotifySearch',side_effect=SpotifyUnavailable('credentials unavailable')),patch('concert_discovery.source_links.apply_candidates',return_value=None),patch('concert_discovery.spotify_matching.match_bandsintown_link',return_value=None):
   run(db_path=self.db,discover_sources=False)
  self.assertEqual(self.job()['state'],'blocked');self.assertEqual(self.job()['attempts'],1)
  self.assertIsNotNone(self.job()['next_attempt_at'])
  run(limit=0,db_path=self.db,discover_sources=False)
  self.assertEqual(self.job()['attempts'],1)
 def test_ambiguity_remains_unlinked(self):
  with patch('concert_discovery.spotify_matching.SpotifySearch'),patch('concert_discovery.source_links.apply_candidates',return_value=None),patch('concert_discovery.spotify_matching.match_bandsintown_link',return_value=None),patch('concert_discovery.spotify_matching.match_artist',return_value='ambiguous_or_no_exact_match'):
   run(db_path=self.db,discover_sources=False)
  self.assertEqual(self.job()['state'],'ambiguous')
  with connect(self.db) as c:self.assertIsNone(c.execute('SELECT spotify_artist_id FROM artists WHERE artist_id=?',(self.job()['artist_id'],)).fetchone()[0])
 def test_verified_identity_survives_import_and_is_not_searched_again(self):
  with connect(self.db) as c:
   c.execute("UPDATE artists SET spotify_artist_id=?,spotify_profile_url=?,match_status='source_link' WHERE artist_id='example'",('A'*22,'https://open.spotify.com/artist/'+'A'*22))
  save_events([self.e],self.db)
  self.assertEqual(self.job()['state'],'matched')
  with patch('concert_discovery.spotify_matching.SpotifySearch') as client:
   run(db_path=self.db,discover_sources=False)
   client.assert_not_called()
 def test_refresh_runs_identity_queue_without_metrics_option(self):
  import concert_discovery.refresh as refresh_module
  with patch.object(refresh_module,'initialize'),patch.object(refresh_module,'fetch_all_calendars',return_value=([],[])),patch.object(refresh_module,'fetch_ticketmaster',return_value=[]),patch.object(refresh_module,'fetch_jambase',return_value=[]),patch.object(refresh_module,'save_events'),patch('concert_discovery.spotify_concert_feed.fetch_feed',return_value=([],None)),patch('concert_discovery.dedupe.cleanup_duplicates',return_value=[]),patch('concert_discovery.matching_queue.run',return_value={'matching_attempted':0}) as worker,patch('pathlib.Path.write_text'):
   refresh_module.refresh(metrics=False,db_path=self.db)
   worker.assert_called_once()
