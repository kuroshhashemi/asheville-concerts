import unittest
from unittest.mock import Mock
from concert_discovery.login_actions import validate,apply
class LoginActionTests(unittest.TestCase):
 def intent(self):return dict(show_key='show',status='Interested',token='abc',stage='signing-in',created_at=1000000)
 def test_action_survives_new_session_and_is_not_a_toggle(self):
  change=validate(self.intent(),{'show'},now=1001);saved={};store=Mock()
  self.assertEqual(apply(change,store,'verified-user',saved),'Unread')
  self.assertEqual(saved,{'show':'Interested'});store.save.assert_called_once_with('verified-user','show','Interested')
  apply(change,store,'verified-user',saved);store.save.assert_called_once();self.assertEqual(saved['show'],'Interested')
 def test_only_login_started_and_known_show_can_resume(self):
  i=self.intent();i['stage']='selected';self.assertIsNone(validate(i,{'show'},now=1001))
  self.assertIsNone(validate(self.intent(),{'other'},now=1001))
  self.assertIsNone(validate(self.intent(),{'show'},now=1700))
  self.assertIsNone(validate(self.intent(),{'show'},now=900))
 def test_aliases_and_three_supported_actions(self):
  for status in ['Pass','Interested','Going']:
   i=self.intent();i.update(show_key='old',status=status)
   self.assertEqual(validate(i,{'show'},{'old':'show'},now=1001)['show_key'],'show')
  i=self.intent();i['status']='Unread';self.assertIsNone(validate(i,{'show'},now=1001))
 def test_failed_write_does_not_claim_success(self):
  saved={};store=Mock();store.save.side_effect=RuntimeError('storage unavailable')
  with self.assertRaises(RuntimeError):apply(validate(self.intent(),{'show'},now=1001),store,'user',saved)
  self.assertEqual(saved,{})
