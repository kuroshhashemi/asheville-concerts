import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from concert_discovery.price_refresh import refresh
from concert_discovery.storage import connect,utc_now
from concert_discovery.source_links import schema,encode_markup

class PriceRefreshTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.sqlite3'
 def tearDown(self):self.tmp.cleanup()
 def shows(self):
  return [{'ticket_url':'https://www.etix.com/ticket/p/'+str(i),'performance_start':'2026-11-01','sources':[]} for i in range(4)]
 def test_blocked_provider_stops_after_one_request_and_is_cached(self):
  with patch('concert_discovery.source_links.requests.get',return_value=Mock(status_code=202,is_redirect=False,text='')) as request:
   result=refresh(self.db,shows=self.shows())
   self.assertEqual(request.call_count,1);self.assertEqual(result['price_providers_blocked'],['etix.com'])
   refresh(self.db,shows=self.shows()[:1]);self.assertEqual(request.call_count,1)
 def test_budget_is_shared_across_pages(self):
  with patch('concert_discovery.source_links.requests.get',return_value=Mock(status_code=200,is_redirect=False,text='<p>No tickets listed</p>')) as request:
   result=refresh(self.db,limit=2,shows=self.shows())
   self.assertEqual(request.call_count,2);self.assertEqual(result['price_page_requests'],2)
 def test_cached_markup_requires_no_request(self):
  with connect(self.db) as c:
   schema(c);c.execute('INSERT INTO identity_page_cache VALUES(?,?,?,?)',(self.shows()[0]['ticket_url'],encode_markup('<p>No tickets listed</p>'),200,utc_now()))
  with patch('concert_discovery.source_links.requests.get') as request:
   result=refresh(self.db,limit=0,shows=self.shows()[:1])
   request.assert_not_called();self.assertEqual(result['price_pages_checked'],1)
