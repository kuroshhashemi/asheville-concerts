import unittest
from unittest.mock import patch,Mock
from concert_discovery.accounts import StatusStore,user_key

class AccountTests(unittest.TestCase):
 def test_stable_identity_not_email(self):
  self.assertEqual(user_key({'sub':'a','email':'old'}),user_key({'sub':'a','email':'new'}))
  self.assertNotEqual(user_key({'sub':'a'}),user_key({'sub':'b'}))
  with self.assertRaises(ValueError):user_key({'email':'alone'})
 def test_scoped_reads_and_writes(self):
  store=StatusStore('https://example.supabase.co/rest/v1','server-secret')
  response=Mock();response.json.return_value=[{'show_key':'concert','status':'Going'}]
  with patch('concert_discovery.accounts.requests.get',return_value=response) as get:
   self.assertEqual(store.load('verified-user'),{'concert':'Going'})
   self.assertEqual(get.call_args.kwargs['params']['user_id'],'eq.verified-user')
   self.assertEqual(get.call_args.args[0],'https://example.supabase.co/rest/v1/user_show_statuses')
  with patch('concert_discovery.accounts.requests.post',return_value=response) as post:
   store.save('verified-user','concert','Interested')
   self.assertEqual(post.call_args.kwargs['json']['user_id'],'verified-user')
   self.assertEqual(post.call_args.kwargs['params']['on_conflict'],'user_id,show_key')
   with self.assertRaises(ValueError):store.save('verified-user','concert','invalid')
   self.assertEqual(post.call_count,1)
 def test_filter_preferences_are_scoped_and_preserve_false(self):
  store=StatusStore('https://example.supabase.co','key')
  response=Mock();response.json.return_value=[{'preferences':{'hide_unknown':False,'statuses':[]}}]
  with patch('concert_discovery.accounts.requests.get',return_value=response) as get:
   self.assertEqual(store.load_filters('person-a'),{'hide_unknown':False,'statuses':[]})
   self.assertEqual(get.call_args.kwargs['params']['user_id'],'eq.person-a')
  with patch('concert_discovery.accounts.requests.post',return_value=response) as post:
   store.save_filters('person-b',{'hide_unknown':True})
   self.assertEqual(post.call_args.kwargs['json']['user_id'],'person-b')
 def test_failures_are_not_reported_as_saved(self):
  response=Mock();response.raise_for_status.side_effect=RuntimeError('offline')
  with patch('concert_discovery.accounts.requests.post',return_value=response):
   with self.assertRaises(RuntimeError):StatusStore('https://example','key').save('user','show','Pass')
if __name__=='__main__':unittest.main()
