import unittest
from datetime import date
from concert_discovery.prices import structured,advertised,from_markup
from concert_discovery.sierra_calendar import parse_api
class PriceCollectionTests(unittest.TestCase):
 def test_usd_only(self):
  self.assertEqual(structured({'priceRanges':[{'currency':'USD','min':25,'max':40}]})['min'],25)
  self.assertIsNone(structured({'offers':[{'price':10,'priceCurrency':'EUR'}]}))
  self.assertIsNone(advertised('No price listed'))
  self.assertEqual(advertised('THIS IS A FREE EVENT!')['min'],0)
 def test_event_json_only(self):
  self.assertEqual(from_markup('<script type="application/ld+json">{"@type":"MusicEvent","offers":{"price":"30","priceCurrency":"USD"}}</script>')['min'],30)
  self.assertIsNone(from_markup('<script type="application/ld+json">{"@type":"Product","offers":{"price":5,"priceCurrency":"USD"}}</script>'))
 def test_sierra_city_and_identity(self):
  base={'title':'Band &#038; Friends','url':'https://sierranevada.com/event/a','start_date':'2026-10-20 19:00:00','description':'THIS IS A FREE EVENT!'}
  rows=parse_api({'events':[{**base,'venue':{'city':'Chico'}},{**base,'venue':{'city':'Mills River'}}]},today=date(2026,10,13))
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['title'],'Band & Friends');self.assertEqual(rows[0]['advertised_price']['min'],0)
