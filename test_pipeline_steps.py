import unittest
from concert_discovery.pipeline_steps import attempt
class PipelineTests(unittest.TestCase):
 def test_provider_failure_does_not_skip_independent_work(self):
  result={};warnings=[]
  def fail():raise RuntimeError('provider unavailable')
  attempt(result,warnings,'Growth',fail)
  attempt(result,warnings,'Prices',lambda:{'prices_saved':1})
  self.assertEqual(result['prices_saved'],1)
  self.assertEqual(result['enrichment_failures'],['Growth'])
  self.assertTrue(warnings)
 def test_programming_error_is_not_disguised_as_provider_failure(self):
  with self.assertRaises(KeyError):attempt({},[],'Growth',lambda:{}['missing'])
