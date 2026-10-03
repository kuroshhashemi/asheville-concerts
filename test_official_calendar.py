import unittest
from datetime import date
from concert_discovery.official_calendar import parse_calendar
class OfficialTests(unittest.TestCase):
 def test_explicit_venue_year_and_duplicate_layout(self):
  event='''<div class="eventWrapper"><div id="eventDate">Fri, Oct 30</div><a id="eventTitle" href="https://example.com/show">Wednesday &amp; Mannequin Pussy</a><h4 id="evSubHead"><a>Snõõper</a></h4><span>Show: 7 pm | Doors: 6 pm</span><a class="venueLink">Hellbender</a><a href="https://www.etix.com/ticket/p/123">Tickets</a></div>'''
  es=parse_calendar('<span class="rhp-events-list-separator-month">October 2026</span>'+event+event,date(2026,10,1))
  self.assertEqual(len(es),1); self.assertEqual(es[0]['venue_id'],'hellbender');self.assertEqual(es[0]['performance_start'],'2026-10-30 19:00:00')
  self.assertIn('Snõõper',[p['name'] for p in es[0]['performers']])
