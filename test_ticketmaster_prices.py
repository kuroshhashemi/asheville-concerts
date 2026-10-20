import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concert_discovery.ticketmaster_prices import Buffer, decode, event_id, refresh

FIXTURES = Path(__file__).parent/'test_fixtures/ticketmaster'

class TicketmasterPricesTests(unittest.TestCase):
 def sample(self,eid='2D006539DA2A5A37'):
  return (FIXTURES/(eid+'.bin')).read_bytes(),(FIXTURES/(eid+'-availability.bin')).read_bytes()
 def test_three_real_samples_match_observed_single_adult_prices(self):
  for eid,minimum in [('2D006539DA2A5A37',51.55),('2D0064EACA0815EB',64.90),('2D0064F18226A7E9',60.30)]:
   price=decode(*self.sample(eid),eid)
   self.assertEqual(price['min'],minimum);self.assertTrue(price['includes_fees']);self.assertEqual(price['quantity'],1)
 def test_student_offer_never_used(self):
  event,available=self.sample();event=event.replace(b'ADULT',b'CHILD')
  self.assertIsNone(decode(event,available,'2D006539DA2A5A37'))
 def test_missing_mandatory_fees_fail_closed(self):
  import struct
  event,available=self.sample();b=Buffer(event);prices=b.obj(b.obj(b.root,0),10)
  event=bytearray(event);struct.pack_into('<I',event,b.obj(prices,4),0)
  with self.assertRaises(ValueError):decode(bytes(event),available,'2D006539DA2A5A37')
 def test_wrong_event_and_version_fail_closed(self):
  event,available=self.sample()
  with self.assertRaises(ValueError):decode(event,available,'2D0064EACA0815EB')
  b=Buffer(event);version=b.text(b.obj(b.root,0),5).encode()
  with self.assertRaises(ValueError):decode(event.replace(version,b'x'*len(version)),available,'2D006539DA2A5A37')
 def test_truncated_buffers_rejected(self):
  event,available=self.sample()
  for n in (0,4,20,100):
   with self.assertRaises(ValueError):decode(event[:n],available,'2D006539DA2A5A37')
 def test_event_url_and_affiliate_identity_not_discovery_or_artist_ids(self):
  self.assertEqual(event_id('https://www.ticketmaster.com/show/event/2d006539da2a5a37'),'2D006539DA2A5A37')
  self.assertEqual(event_id('https://ticketmaster.evyy.net/c/123?u=https%3A%2F%2Fwww.ticketmaster.com%2Fevent%2F2D006539DA2A5A37'),'2D006539DA2A5A37')
  for u in ['https://evil.org/event/2D006539DA2A5A37','https://ticketmaster.com.evil.org/event/2D006539DA2A5A37','https://www.ticketmaster.com/event/Z7r9jZ1AAZ-A-']:
   self.assertIsNone(event_id(u))
 def test_daily_failure_and_success_cache_and_aliases(self):
  shows=[{'ticket_url':'https://venue.org/show','sources':[{'source_url':'https://www.ticketmaster.com/slug/event/2D006539DA2A5A37'}]}]*2
  with tempfile.TemporaryDirectory() as tmp,patch('concert_discovery.ticketmaster_prices.fetch',return_value={'min':51.55,'max':82.41,'includes_fees':True}) as fetch,patch('concert_discovery.ticketmaster_prices.save') as save:
   db=Path(tmp)/'test.sqlite3';refresh(db,shows=shows);refresh(db,shows=shows)
   self.assertEqual(fetch.call_count,1);self.assertEqual(save.call_count,2)
  with tempfile.TemporaryDirectory() as tmp,patch('concert_discovery.ticketmaster_prices.fetch',side_effect=ValueError('blocked')) as fetch,patch('concert_discovery.ticketmaster_prices.save') as save:
   db=Path(tmp)/'test.sqlite3';refresh(db,shows=shows);refresh(db,shows=shows)
   self.assertEqual(fetch.call_count,1);save.assert_not_called()
 def test_priced_event_is_rechecked_after_one_day(self):
  from datetime import datetime,timezone,timedelta
  from concert_discovery.storage import connect
  shows=[{'ticket_url':'https://www.ticketmaster.com/event/2D006539DA2A5A37','sources':[]}]
  with tempfile.TemporaryDirectory() as tmp,patch('concert_discovery.ticketmaster_prices.fetch',return_value={'min':20,'max':20}) as fetch,patch('concert_discovery.ticketmaster_prices.save'):
   db=Path(tmp)/'test.sqlite3';refresh(db,shows=shows)
   with connect(db) as c:c.execute('UPDATE ticketmaster_price_checks SET checked_at=?',((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),))
   refresh(db,shows=shows);self.assertEqual(fetch.call_count,2)
 def test_limit_and_ambiguous_event_ids(self):
  shows=[{'ticket_url':f'https://www.ticketmaster.com/event/{i:016X}','sources':[]} for i in range(5)]
  with tempfile.TemporaryDirectory() as tmp,patch('concert_discovery.ticketmaster_prices.fetch',return_value=None) as fetch:
   refresh(Path(tmp)/'test.sqlite3',limit=2,shows=shows);self.assertEqual(fetch.call_count,2)
  shows[0]['sources']=[{'source_url':shows[1]['ticket_url']}]
  with tempfile.TemporaryDirectory() as tmp,patch('concert_discovery.ticketmaster_prices.fetch') as fetch:
   refresh(Path(tmp)/'test.sqlite3',shows=shows[:1]);fetch.assert_not_called()

 def test_digest_requires_inventory_attempt_not_just_cached_venue_page(self):
  from concert_discovery.digest_readiness import audit
  from concert_discovery.storage import connect,utc_now
  from concert_discovery.source_links import schema,encode_markup
  url='https://www.ticketmaster.com/event/2D006539DA2A5A37'
  show={'show_id':1,'title':'Example','ticket_url':url,'sources':[{'source_url':url}],'headliners':[]}
  with tempfile.TemporaryDirectory() as tmp,patch('concert_discovery.digest_readiness.load',return_value={}):
   db=Path(tmp)/'test.sqlite3'
   with connect(db) as c:
    schema(c);c.execute('INSERT INTO identity_page_cache VALUES(?,?,?,?)',(url,encode_markup('<h1>Example</h1>'),200,utc_now()))
   self.assertEqual(audit([show],db)[0]['pending'],['ticket price'])
   with patch('concert_discovery.ticketmaster_prices.fetch',return_value=None):refresh(db,shows=[show])
   self.assertEqual(audit([show],db),[])
