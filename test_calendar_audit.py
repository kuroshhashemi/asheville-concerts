import unittest
from concert_discovery.calendar_audit import collect_pages
class AuditTests(unittest.TestCase):
 def test_pagination_must_finish_before_snapshot(self):
  docs={'https://example.com/one':'<div class="rhp-pagination"><a href="/two">Next</a></div>','https://example.com/two':'<p>end</p>'}
  rows,pages=collect_pages('https://example.com/one',docs.__getitem__,lambda text:[{'source_key':text,'source_url':text}])
  self.assertEqual(pages,2)
  with self.assertRaises(ValueError):collect_pages('https://example.com/one',docs.__getitem__,lambda text:[{'source_key':text}],max_pages=1)
 def test_unparsed_card_cannot_retire(self):
  with self.assertRaises(ValueError):collect_pages('https://example.com',lambda u:'<div class="eventWrapper"><a id="eventTitle" href="lost">Real band</a></div>',lambda h:[{'source_key':'other','source_url':'other'}])
