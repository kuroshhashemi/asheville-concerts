import unittest
from concert_discovery.availability import text_availability,structured_availability,ticket_page_status
class AvailabilityTests(unittest.TestCase):
 def test_ticket_notice_is_scoped(self):
  url='https://www.etix.com/ticket/p/123'
  self.assertEqual(ticket_page_status(url,'<p>This performance is sold out.</p>'),'sold_out')
  self.assertIsNone(ticket_page_status(url,'<p>The artist sold out their previous tour.</p>'))
  self.assertIsNone(ticket_page_status(url,'<p>Security challenge</p>'))
  self.assertEqual(ticket_page_status(url,'<div role="combobox" aria-label="Adult Price: $30"></div>'),'available')
 def test_related_ticket_upsell_is_not_availability(self):
  url='https://wl.eventim.us/event/test/123'
  self.assertIsNone(ticket_page_status(url,'<div id="eventview"><div id="addtomyorder_1"><p>Sold Out</p></div></div>'))
  self.assertEqual(ticket_page_status(url,'<div id="eventview"><p>Sold Out</p></div>'),'sold_out')
 def test_only_explicit_sold_out(self):
  self.assertEqual(text_availability('Artist — SOLD OUT'), 'sold_out')
  self.assertIsNone(text_availability('Artist — Tickets'))
 def test_mixed_offers_are_not_sold_out(self):
  self.assertEqual(structured_availability({'offers':[{'availability':'https://schema.org/SoldOut'},{'availability':'https://schema.org/InStock'}]}),'available')
  self.assertEqual(structured_availability({'offers':{'availability':'https://schema.org/SoldOut'}}),'sold_out')
  self.assertIsNone(structured_availability({'offers':{'availability':'https://schema.org/OutOfStock'}}))
