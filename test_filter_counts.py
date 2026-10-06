import unittest
from concert_discovery.filter_counts import counts
class FacetTests(unittest.TestCase):
 def test_other_filters_apply_and_genre_does_not_double_count_all(self):
  rows=[dict(title='A',venue_name='V1',audience=10000,listener_growth_6m=None,decision=None,headliners=[],event_classification={'category':'live_music'},genres={'Indie','Rock'}),dict(title='B',venue_name='V2',audience=None,listener_growth_6m=None,decision='going',headliners=[],event_classification={'category':'comedy'},genres={'Unknown'})]
  c,total=counts(rows,['V1'],['Indie','Rock','Unknown'],['Live Music','Comedy'],['Unread','Going'],(0,100),False,(-100,100),(-100,100),'',lambda s:s['genres'])
  self.assertEqual(c['venue'],{'V1':1,'V2':1})
  self.assertEqual(c['type'],{'Live Music':1})
  self.assertEqual(c['genre'],{'Indie':1,'Rock':1})
  self.assertEqual(total['genre'],1)
