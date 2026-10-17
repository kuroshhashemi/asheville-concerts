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

 def test_future_sale_button_and_expired_date(self):
  from concert_discovery.availability import future_sale_label
  self.assertEqual(future_sale_label('2099-10-03'), 'On Sale 10/3')
  self.assertIsNone(future_sale_label('2000-10-03'))
  self.assertIsNone(future_sale_label('invalid'))

 def test_tixr_waitlist_is_sold_out_but_mixed_inventory_is_not(self):
  url='https://www.tixr.com/groups/test/events/show-123'
  queued='<div class="ticket" data-row-type="primary" data-product-state="QUEUED">Waitlist</div>'
  self.assertEqual(ticket_page_status(url,queued),'sold_out')
  self.assertEqual(ticket_page_status(url,queued+'<div class="ticket" data-row-type="primary" data-product-state="OPEN">Tickets</div>'),'available')
  self.assertIsNone(ticket_page_status(url,'<p>Join our mailing list waitlist</p>'))

 def test_ticketmaster_requires_explicit_notice_not_empty_inventory(self):
  url='https://www.ticketmaster.com/event/123'
  self.assertEqual(ticket_page_status(url,'<h2>This event is sold out.</h2>'),'sold_out')
  self.assertIsNone(ticket_page_status(url,'<p>0 seats available</p><p>The artist sold out last year.</p>'))
  self.assertEqual(ticket_page_status(url,'<ul role="menu" aria-label="Ticket listings sorted by lowest price"><li><button>Select Verified Resale Ticket $150</button></li></ul>'),'available')
