import unittest
from concert_discovery.digest_validation import conflicts
class ConflictTests(unittest.TestCase):
 def row(self,i,time,official=False):
  return dict(show_id=i,title='Same artist',venue_id='venue',performance_start=time,ticket_url='',headliners=[dict(artist_id='artist',display_name='Same artist')],sources=[dict(source_name='Venue Official' if official else 'JamBase')])
 def test_cross_day_time_conflict_is_held(self):
  a=self.row(1,'2027-02-04 23:30:00');b=self.row(2,'2027-02-05 20:00:00')
  self.assertTrue(conflicts([a],[a,b]))
 def test_separate_official_nights_are_preserved(self):
  a=self.row(1,'2027-02-04 20:00:00',True);b=self.row(2,'2027-02-05 20:00:00',True)
  self.assertEqual(conflicts([a],[a,b]),[])
 def test_distant_dates_are_not_conflicts(self):
  a=self.row(1,'2027-02-04 20:00:00');b=self.row(2,'2027-03-05 20:00:00')
  self.assertEqual(conflicts([a],[a,b]),[])
 def test_distinct_verified_official_event_pages_allow_two_dates(self):
  a=self.row(1,'2027-02-04 23:30:00');b=self.row(2,'2027-02-05 23:30:00')
  self.assertEqual(conflicts([a],[a,b],{1:'https://venue.org/event/one',2:'https://venue.org/event/two'}),[])
