import unittest
from concert_discovery.reconciliation import same_bill
class ReconciliationTests(unittest.TestCase):
 def test_typo_and_project_suffix(self):
  self.assertTrue(same_bill('Noah Gundersen','Noah Gunderson'))
  self.assertTrue(same_bill("CLAUDIO SIMONETTI'S GOBLIN / TENEBRE",'Claudio Simonetti'))
 def test_distinct_names_stay_distinct(self):
  self.assertFalse(same_bill('The Midnight','The Midnight Riders'))
  self.assertFalse(same_bill('Noah Kahan','Noah Gundersen'))

class DuplicateSafetyTests(unittest.TestCase):
 def test_same_night_duplicate_but_preserve_two_dates_and_two_times(self):
  from concert_discovery.reconciliation import reconcile
  def show(i,title,start,official):return dict(show_id=i,title=title,venue_id='eulogy',performance_start=start,sources=[{'source_name':'EulogyOfficial' if official else 'Songkick'}],headliners=[])
  first=show(1,'PROJECT PAT','2026-10-16 20:00:00',True)
  second=show(2,'PROJECT PAT - NIGHT 2','2026-10-17 20:00:00',True)
  duplicate=show(3,'Project Pat','2026-10-17 20:00:00',False)
  late=show(4,'Project Pat','2026-10-17 23:00:00',True)
  self.assertEqual([s['show_id'] for s in reconcile([first,second,duplicate,late])],[1,2,4])

class DoorTimeTests(unittest.TestCase):
 def test_one_official_bill_catches_nearby_provider_time_but_not_two_official_shows(self):
  from concert_discovery.reconciliation import reconcile
  def show(i,time,source):return dict(show_id=i,title='A Band',venue_id='sierra-nevada',performance_start='2026-11-12 '+time,sources=[dict(source_name=source)],headliners=[])
  official=show(1,'18:00:00','SierraOfficial');provider=show(2,'18:30:00','Songkick')
  self.assertEqual([s['show_id'] for s in reconcile([official,provider])],[1])
  second=show(3,'19:00:00','SierraOfficial')
  self.assertEqual(len(reconcile([official,provider,second])),3)
