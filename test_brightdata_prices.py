import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from concert_discovery.brightdata_prices import refresh,reserve
class BrightPricesTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.db=Path(self.t.name)/'catalog.sqlite3'
  self.shows=[{'performance_start':'2099-01-01','ticket_url':'https://www.etix.com/ticket/p/'+str(i),'sources':[]} for i in range(3)]
 def tearDown(self):self.t.cleanup()
 def test_atomic_budget_stops(self):
  with patch('concert_discovery.brightdata_prices.MONTHLY_LIMIT',2):
   self.assertTrue(reserve(self.db));self.assertTrue(reserve(self.db));self.assertFalse(reserve(self.db))
 def test_cache_and_per_run_limit(self):
  with patch('concert_discovery.brightdata_prices.secret',return_value='test'),patch('concert_discovery.brightdata_prices.load',return_value={}),patch('concert_discovery.brightdata_prices.save'),patch('concert_discovery.brightdata_prices.requests.post',return_value=Mock(status_code=200,text='<div role="combobox" aria-label="Adult, Price: $25"></div>')) as request:
   result=refresh(self.db,limit=1,shows=self.shows)
   self.assertEqual(result['brightdata_prices_saved'],1);self.assertEqual(request.call_count,1)
   refresh(self.db,shows=self.shows[:1]);self.assertEqual(request.call_count,1)
 def test_authorization_or_balance_failure_stops_batch(self):
  with patch('concert_discovery.brightdata_prices.secret',return_value='test'),patch('concert_discovery.brightdata_prices.load',return_value={}),patch('concert_discovery.brightdata_prices.requests.post',return_value=Mock(status_code=402)) as request:
   result=refresh(self.db,shows=self.shows)
   self.assertEqual(request.call_count,1);self.assertEqual(result['brightdata_state'],'http_402')
