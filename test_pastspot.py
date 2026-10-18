import unittest
from datetime import date
from concert_discovery.pastspot import comparison

class HistoryTests(unittest.TestCase):
    def rows(self, baseline=100, latest=150):
        return [dict(observed_date='2026-04-03',listeners=baseline,source_url='https://pastspot.com/test'),
                dict(observed_date='2026-10-02',listeners=latest,source_url='https://pastspot.com/test')]
    def test_dated_comparison(self):
        value=comparison(self.rows(),date(2026,10,4))
        self.assertEqual(value['value'],50)
        self.assertEqual(value['baseline_date'],'2026-04-03')
    def test_missing_zero_and_stale_are_not_growth(self):
        self.assertIsNone(comparison(self.rows()[1:],date(2026,10,4)))
        self.assertIsNone(comparison(self.rows(0),date(2026,10,4)))
        self.assertIsNone(comparison(self.rows(),date(2026,11,4)))
    def test_zero_current_is_valid_decline(self):
        self.assertEqual(comparison(self.rows(latest=0),date(2026,10,4))['value'],-100)

class HistoryFailureTests(unittest.TestCase):
 def test_blocked_history_attempt_is_recorded_without_deleting_old_history(self):
  import tempfile
  from pathlib import Path
  from datetime import timedelta
  from unittest.mock import patch,Mock
  from concert_discovery.storage import initialize,connect
  from concert_discovery.api_sources import event
  from concert_discovery.refresh import save_events
  from concert_discovery.pastspot import save,refresh_history
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'test.sqlite3';initialize(db)
   e=event('EulogyOfficial','https://example.com/show','Example',(date.today()+timedelta(days=30)).isoformat(),'eulogy',[{'name':'Example','role':'headliner','confidence':1}]);save_events([e],db)
   sid='a'*22
   with connect(db) as c:c.execute("UPDATE artists SET spotify_artist_id=?,spotify_profile_url=?",(sid,'https://open.spotify.com/artist/'+sid))
   save(sid,[{'date':'2026-04-01','listeners':100}],'https://pastspot.com/test','history',db)
   with connect(db) as c:c.execute("UPDATE history_checks SET checked_at='2020-01-01T00:00:00+00:00'")
   with patch('concert_discovery.pastspot.requests.get',return_value=Mock(status_code=403)) as request:refresh_history(db,limit=1)
   with connect(db) as c:
    self.assertEqual(c.execute('SELECT status FROM history_checks').fetchone()[0],'blocked')
    self.assertEqual(c.execute('SELECT count(*) FROM listener_history').fetchone()[0],1)
