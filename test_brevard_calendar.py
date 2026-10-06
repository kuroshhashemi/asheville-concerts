import unittest
from datetime import date
from concert_discovery.brevard_calendar import parse, fetch_brevard

def card(title='Season Opener with Stile Antico',day='Sunday, October 18, 2026, 3:00 pm',suffix='a'):
 return '<article class="type-event"><h1><a href="https://www.brevardmusic.org/event/'+suffix+'/">'+title+'</a></h1><div class="date">'+day+'</div><a class="tickets" href="https://secured.brevardmusic.org/123">Buy Tickets</a></article>'
class BrevardTests(unittest.TestCase):
 def test_artist_and_date(self):
  rows,_=parse(card(),date(2026,10,5));self.assertEqual(rows[0]['performers'][0]['name'],'Stile Antico');self.assertEqual(rows[0]['performance_start'],'2026-10-18 15:00:00')
 def test_bad_card_disables_retirement(self):
  with self.assertRaises(ValueError):parse(card()+card(day='Unknown'))
 def test_pagination_and_distinct_dates(self):
  pages={'https://www.brevardmusic.org/events/':card()+'<a class="next page-numbers" href="/events/page/2/">Next</a>', 'https://www.brevardmusic.org/events/page/2/':card('Django Festival Allstars','Tuesday, November 10, 2026, 7:30 pm','b')}
  rows,snap=fetch_brevard(pages.__getitem__);self.assertEqual(len(rows),2);self.assertEqual(snap[0]['pages'],2)
 def test_composition_is_not_an_artist(self):
  rows,_=parse(card('Handel’s Messiah'),date(2026,10,5));self.assertEqual(rows[0]['performers'],[])
