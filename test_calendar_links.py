import unittest
from urllib.parse import urlsplit,parse_qs
from concert_discovery.calendar_links import google_calendar_link
class CalendarLinkTests(unittest.TestCase):
 def test_local_time_and_private_target(self):
  show={'performance_start':'2026-10-04 20:00:00','timezone':'America/New_York','venue_name':'Venue & Room'}
  q=parse_qs(urlsplit(google_calendar_link(show,'Artist & Band','https://tickets.example/?a=1&b=2','family@example.com')).query)
  self.assertEqual(q['dates'],['20261005T000000Z/20261005T030000Z'])
  self.assertEqual(q['src'],['family@example.com'])
  self.assertEqual(q['text'],['Artist & Band'])
  self.assertNotIn('src',parse_qs(urlsplit(google_calendar_link(show,'Artist','https://tickets.example')).query))
 def test_unknown_time_is_all_day_not_invented(self):
  show={'performance_start':'2026-11-13 00:00:00','venue_name':'Venue'}
  q=parse_qs(urlsplit(google_calendar_link(show,'Band','https://tickets.example')).query)
  self.assertEqual(q['dates'],['20261113/20261114'])
if __name__=='__main__':unittest.main()
