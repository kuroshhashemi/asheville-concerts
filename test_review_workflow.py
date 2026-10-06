import unittest
from concert_discovery.review_workflow import select_view
class ReviewWorkflowTests(unittest.TestCase):
 def setUp(self):
  self.shows=[{'show_id':i,'decision':d} for i,d in enumerate((None,'interested','going','passed'))]
 def ids(self,*args,**kwargs):return [s['show_id'] for s in select_view(self.shows,*args,**kwargs)]
 def test_views_partition_reviewed_and_unreviewed(self):
  self.assertEqual(self.ids('To review'),[0])
  self.assertEqual(self.ids('Saved'),[1,2])
  self.assertEqual(self.ids('Hidden'),[3])
  self.assertEqual(self.ids('Saved','Interested'),[1])
  self.assertEqual(self.ids('Saved','Going'),[2])
 def test_hidden_only_opted_into_all(self):
  self.assertEqual(self.ids('All'),[0,1,2,3])
  self.assertEqual(self.ids('To Review'),[0,1,2])
  self.assertEqual(self.ids('All',hide_hidden=False),[0,1,2,3])
 def test_review_action_and_undo(self):
  self.shows[0]['decision']='interested'
  self.assertEqual(self.ids('To review'),[])
  self.assertEqual(self.ids('Saved'),[0,1,2])
  self.shows[0]['decision']=None
  self.assertEqual(self.ids('To review'),[0])
