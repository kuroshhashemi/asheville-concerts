import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from concert_discovery.brightdata_guard import reserve_growth
class FreeOnlyGuardTests(unittest.TestCase):
 def run_policy(self,policy,reserved=True):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'policy.json';p.write_text(json.dumps(policy))
   with patch('concert_discovery.brightdata_guard.POLICY',p),patch('concert_discovery.brightdata_guard.secret',return_value='test'),patch('concert_discovery.brightdata_guard.reserve',return_value=reserved) as reserve:
    result=reserve_growth(Path(tmp)/'db');return result,reserve.call_count
 def test_verified_unfunded_account_reserves_shared_request(self):
  result,n=self.run_policy({'paid_balance':0,'auto_recharge_off':True,'owner_confirmed_at':'2026-10-21'})
  self.assertTrue(result[0]);self.assertEqual(n,1)
 def test_funded_unknown_or_recharging_account_blocks_without_reservation(self):
  for p in ({},{'paid_balance':10,'auto_recharge_off':True,'owner_confirmed_at':'today'},{'paid_balance':0,'auto_recharge_off':False,'owner_confirmed_at':'today'}):
   result,n=self.run_policy(p);self.assertFalse(result[0]);self.assertEqual(n,0)
 def test_shared_budget_exhaustion_stops_request(self):
  result,n=self.run_policy({'paid_balance':0,'auto_recharge_off':True,'owner_confirmed_at':'today'},False)
  self.assertFalse(result[0]);self.assertEqual(n,1)
