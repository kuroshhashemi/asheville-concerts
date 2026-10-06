import unittest
from concert_discovery.availability import text_availability,structured_availability
class AvailabilityTests(unittest.TestCase):
 def test_only_explicit_sold_out(self):
  self.assertEqual(text_availability('Artist — SOLD OUT'), 'sold_out')
  self.assertIsNone(text_availability('Artist — Tickets'))
 def test_mixed_offers_are_not_sold_out(self):
  self.assertEqual(structured_availability({'offers':[{'availability':'https://schema.org/SoldOut'},{'availability':'https://schema.org/InStock'}]}),'available')
  self.assertEqual(structured_availability({'offers':{'availability':'https://schema.org/SoldOut'}}),'sold_out')
  self.assertIsNone(structured_availability({'offers':{'availability':'https://schema.org/OutOfStock'}}))
