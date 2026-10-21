import unittest
from unittest.mock import patch,Mock
from concert_discovery.brightdata_guard import reserve_growth
class FreeOnlyGuardTests(unittest.TestCase):
 def test_permission_denied_never_authorizes_spend(self):
  with patch('concert_discovery.brightdata_guard.secret',return_value='test'),patch('concert_discovery.brightdata_guard.requests.get',return_value=Mock(ok=False,status_code=403)),patch('concert_discovery.brightdata_guard.requests.post') as post:
   ok,reason=reserve_growth(None);self.assertFalse(ok);self.assertIn('403',reason);post.assert_not_called()
 def test_wallet_balance_is_not_free_credit_authorization(self):
  r=Mock(ok=True);r.json.return_value={'balance':100,'free_credits':5000}
  with patch('concert_discovery.brightdata_guard.secret',return_value='test'),patch('concert_discovery.brightdata_guard.requests.get',return_value=r):self.assertFalse(reserve_growth(None)[0])
