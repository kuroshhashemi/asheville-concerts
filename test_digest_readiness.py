import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from concert_discovery.storage import initialize,connect
from concert_discovery.digest_readiness import audit,require_ready
class ReadinessTests(unittest.TestCase):
 def test_unattempted_matching_and_price_are_pending(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'catalog.sqlite3';initialize(db)
   s={'show_id':1,'title':'Example','sources':[{'source_url':'https://example.org/show'}],'headliners':[{'artist_id':'example','display_name':'Example'}],'ticket_url':'https://example.org/ticket'}
   with patch('concert_discovery.digest_readiness.load',return_value={}):
    self.assertIn('ticket price',audit([s],db)[0]['pending'])
    with self.assertRaisesRegex(RuntimeError,'Digest held'):require_ready([s],db)
 def test_recorded_unavailable_checks_are_distinct_from_unattempted(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'catalog.sqlite3';initialize(db)
   from concert_discovery.matching_queue import schema
   with connect(db) as c:
    schema(c);c.execute("INSERT INTO artist_matching_jobs(artist_id,name,state,attempts) VALUES('example','Example','ambiguous',1)")
    c.execute('CREATE TABLE ticket_price_checks(url_key TEXT PRIMARY KEY)');c.execute("INSERT INTO ticket_price_checks VALUES('example.org/ticket')")
   s={'show_id':1,'title':'Example','sources':[{'source_url':'https://example.org/show'}],'headliners':[{'artist_id':'example','display_name':'Example'}],'ticket_url':'https://example.org/ticket'}
   with patch('concert_discovery.digest_readiness.load',return_value={}):self.assertEqual(audit([s],db),[])
