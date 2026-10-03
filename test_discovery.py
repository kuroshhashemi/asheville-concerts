import tempfile,unittest
from pathlib import Path
from datetime import date
from concert_discovery.storage import initialize,connect,upsert_show,add_metric_snapshot,save_manual_spotify_match
from concert_discovery.discovery import get_shows,select_shows,decide,six_month_growth,filter_table,compact_audience
class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.sqlite3';initialize(self.db)
  event=dict(venue_id='orange-peel',title='Headline with Support',performance_start=date.today().isoformat()+' 20:00:00',date_status='feed_only',source_key='test',source_name='test',source_event_id='1',source_url='https://example.com',performers=[dict(name='Headline',role='headliner',confidence=1),dict(name='Support',role='support',confidence=1)])
  with connect(self.db) as c:self.show=upsert_show(c,event)
  for aid,count,sid in [('headline',300000,'A'*22),('support',5000000,'B'*22)]:
   save_manual_spotify_match(aid,sid,self.db)
   with connect(self.db) as c:add_metric_snapshot(c,aid,followers=10,monthly_listeners=count,status='success',source_url='https://open.spotify.com/artist/'+sid)
 def tearDown(self):self.tmp.cleanup()
 def test_shortlist_uses_headliners_not_popular_support(self):
  shows=get_shows(self.db);self.assertEqual(shows[0]['audience'],300000)
  self.assertEqual(len(select_shows(shows,minimum=250000)),1)
  self.assertEqual(len(select_shows(shows,minimum=500000)),0)
 def test_pass_persists_and_undo_restores_shortlist(self):
  decide(self.show,'passed',self.db);self.assertEqual(select_shows(get_shows(self.db)),[])
  decide(self.show,None,self.db);self.assertEqual(len(select_shows(get_shows(self.db))),1)
  decide(self.show,'interested',self.db);self.assertEqual(len(select_shows(get_shows(self.db),view='Interested')),1)
 def test_replaced_profile_does_not_use_old_metrics(self):
  save_manual_spotify_match('headline','C'*22,self.db)
  self.assertEqual(select_shows(get_shows(self.db)),[])
 def test_growth_requires_six_month_baseline_and_is_independent_of_audience(self):
  history=[dict(retrieved_at='2026-04-03T12:00:00+00:00',monthly_listeners=100),dict(retrieved_at='2026-10-03T12:00:00+00:00',monthly_listeners=150)]
  self.assertAlmostEqual(six_month_growth(history),50)
  self.assertIsNone(six_month_growth(history[1:]))
  self.assertIsNone(six_month_growth([dict(retrieved_at='2026-09-03',monthly_listeners=100)]+history[1:]))
  shows=[dict(venue_name='A',decision=None,audience=150,listener_growth_6m=50),dict(venue_name='A',decision=None,audience=5000000,listener_growth_6m=None)]
  self.assertEqual(filter_table(shows,['A'],['Unread'],minimum_growth=40),shows[:1])
  self.assertEqual(compact_audience(5512000),'5,512k')

 def test_users_have_separate_decisions(self):
  decide(self.show,'passed',self.db,user_id='alice')
  decide(self.show,'interested',self.db,user_id='bob')
  self.assertEqual(get_shows(self.db,user_id='alice')[0]['decision'],'passed')
  self.assertEqual(get_shows(self.db,user_id='bob')[0]['decision'],'interested')
  self.assertIsNone(get_shows(self.db,user_id='new-user')[0]['decision'])
