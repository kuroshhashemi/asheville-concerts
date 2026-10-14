import unittest
from concert_discovery.client_preferences import normalize
class ClientPreferencesTests(unittest.TestCase):
 def norm(self,value):return normalize(value,['A','B'],['Indie'],['Live Music','Comedy'],9700,[-100,400])
 def test_review_selection_is_always_defined_and_saved_views_survive(self):
  self.assertEqual(self.norm({'review_view':None})['review_view'],'To Review')
  for view in ['To Review','Hidden','Interested','Going','All']:self.assertEqual(self.norm({'review_view':view})['review_view'],view)
 def test_bounds_and_invalid_payloads(self):
  p=self.norm({'listener_range':[999999,-3],'growth_range':[float('nan'),10],'excluded_venues':['A','A','missing'],'query':'x'*500})
  self.assertIsNone(p['listener_range']);self.assertIsNone(p['growth_range']);self.assertEqual(p['excluded_venues'],['A']);self.assertEqual(len(p['query']),200)
 def test_zero_minimum_and_hide_unknown_are_preserved(self):
  p=self.norm({'listener_range':[0,500],'hide_unknown':False})
  self.assertEqual(p['listener_range'],[0,500]);self.assertFalse(p['hide_unknown'])
