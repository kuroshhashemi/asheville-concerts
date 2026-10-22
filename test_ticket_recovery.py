import unittest
from unittest.mock import Mock,patch
from concert_discovery.availability import ticket_page_status,access_condition
from concert_discovery.prices import from_ticket_markup
class RecoveryTests(unittest.TestCase):
 def test_eventim_not_available_in_sold_out_widget_only(self):
  u='https://wl.eventim.us/event/test/123'
  self.assertEqual(ticket_page_status(u,'<div id="eventview"><div class="sold-out-info-box"><p>Tickets are not available</p></div></div>'),'sold_out')
  self.assertIsNone(ticket_page_status(u,'<div id="eventview"><p>Tickets are not available</p></div>'))
  self.assertEqual(ticket_page_status(u,'<div id="main" class="event-pg"><div class="sold-out-info-box">Tickets are not available</div></div>'),'sold_out')
  self.assertIsNone(ticket_page_status(u,'<div id="main" class="event-pg"><div class="after-event-recommendations"><div class="sold-out-info-box">Tickets are not available</div></div></div>'))
 def test_password_gate_is_not_sold_out(self):
  html='<form id="eventpassform"><p>A password is required to buy tickets to this event.</p></form>'
  self.assertEqual(access_condition('https://wl.eventim.us/event/test/123',html),'password_required')
  self.assertIsNone(ticket_page_status('https://wl.eventim.us/event/test/123',html))
 def test_etix_total_without_aria_label_and_student_excluded(self):
  html='<div>Price details for ADVANCED: Ticket Price: $33.00, Ticket Fee: $9.83, Total per ticket including taxes: From $43.52 to $46.88</div><div>Student Total per ticket including taxes: $15.00</div>'
  p=from_ticket_markup('https://www.etix.com/ticket/p/123',html)
  self.assertEqual(p['min'],43.52);self.assertEqual(p['max'],46.88)
 def test_brevard_visits_all_section_names_without_selecting_seats(self):
  from concert_discovery.brevard_pricing import collect
  page=Mock();page.url='https://secured.brevardmusic.org/1950/1966'
  page.locator.return_value.get_by_role.return_value.all_text_contents.return_value=['High-Top','Social','Cabaret']
  page.get_by_role.return_value.get_attribute.return_value='false'
  page.get_by_role.return_value.count.return_value=1
  page.content.side_effect=['a','b','c']
  with patch('concert_discovery.prices.from_ticket_markup',side_effect=[{'min':87.53,'max':87.53},{'min':65,'max':65},{'min':90,'max':90}]):
   self.assertEqual(collect(page)['min'],65)
  names=[call.kwargs.get('name') for call in page.locator.return_value.get_by_role.call_args_list]
  self.assertEqual(names[1:],['High-Top','Social','Cabaret'])
