import unittest
from unittest.mock import Mock,patch
from concert_discovery.activity import ActivityStore,is_owner

class ActivityTests(unittest.TestCase):
 def test_identity_and_timestamp_preserve_first_visit(self):
  store=ActivityStore('https://example.com/rest/v1','secret')
  with patch('concert_discovery.activity.requests.post',return_value=Mock()) as post:
   store.touch('verified-id',{'email':'a@example.com','name':'A','email_verified':True})
   payload=post.call_args.kwargs['json']
   self.assertEqual(payload['user_id'],'verified-id')
   self.assertNotIn('first_seen_at',payload)
   self.assertIn('last_active_at',payload)
   with self.assertRaises(ValueError):store.touch('id',{'email':'a','email_verified':False})
 def test_owner_guard(self):
  self.assertTrue(is_owner({'email':'OWNER@example.com'},'owner@example.com'))
  self.assertFalse(is_owner({'email':'friend@example.com'},'owner@example.com'))
  self.assertFalse(is_owner({'email':'owner@example.com','email_verified':False},'owner@example.com'))
  self.assertFalse(is_owner({'email':'owner@example.com'},None))
 def test_current_counts_not_click_history(self):
  users=Mock();users.json.return_value=[{'user_id':'a','email':'a@example.com'}]
  statuses=Mock();statuses.json.return_value=[{'user_id':'a','status':'Going'},{'user_id':'a','status':'Unread'},{'user_id':'b','status':'Pass'}]
  with patch('concert_discovery.activity.requests.get',side_effect=[users,statuses]):
   row=ActivityStore('https://example.com','s').overview()[0]
   self.assertEqual((row['going'],row['hidden'],row['interested']),(1,0,0))
