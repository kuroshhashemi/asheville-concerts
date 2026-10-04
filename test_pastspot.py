import unittest
from datetime import date
from concert_discovery.pastspot import comparison

class HistoryTests(unittest.TestCase):
    def rows(self, baseline=100, latest=150):
        return [dict(observed_date='2026-04-03',listeners=baseline,source_url='https://pastspot.com/test'),
                dict(observed_date='2026-10-02',listeners=latest,source_url='https://pastspot.com/test')]
    def test_dated_comparison(self):
        value=comparison(self.rows(),date(2026,10,4))
        self.assertEqual(value['value'],50)
        self.assertEqual(value['baseline_date'],'2026-04-03')
    def test_missing_zero_and_stale_are_not_growth(self):
        self.assertIsNone(comparison(self.rows()[1:],date(2026,10,4)))
        self.assertIsNone(comparison(self.rows(0),date(2026,10,4)))
        self.assertIsNone(comparison(self.rows(),date(2026,11,4)))
    def test_zero_current_is_valid_decline(self):
        self.assertEqual(comparison(self.rows(latest=0),date(2026,10,4))['value'],-100)
