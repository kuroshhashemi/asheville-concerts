import unittest,tempfile
from pathlib import Path
from concert_discovery.storage import initialize,connect,upsert_show
from concert_discovery.reconciliation import duplicate
from concert_discovery.dedupe import cleanup_duplicates
from concert_discovery.collection_health import start,observation
from concert_discovery.bill_evidence import inspect

class ReliabilityTests(unittest.TestCase):
 def test_partial_import_does_not_mark_other_venues_incomplete(self):
  from concert_discovery.collection_health import missing_checks
  db=self.db
  rid=start(db);warnings=[]
  missing_checks(rid,{'brevard-music-center'},warnings,db)
  with connect(db) as c:self.assertEqual(c.execute('SELECT count(*) FROM collection_health WHERE run_id=?',(rid,)).fetchone()[0],0)
  self.assertEqual(warnings,[])
 def test_full_refresh_records_expected_missing_calendars(self):
  from concert_discovery.collection_health import missing_checks
  rid=start(self.db);warnings=[]
  missing_checks(rid,{'orange-peel'},warnings,self.db,expected_venues={'orange-peel','eulogy'})
  with connect(self.db) as c:self.assertEqual([tuple(r) for r in c.execute('SELECT venue_id,status FROM collection_health WHERE run_id=?',(rid,))],[('eulogy','incomplete')])
  self.assertEqual(len(warnings),1)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'db';initialize(self.db)
 def tearDown(self):self.tmp.cleanup()
 def event(self,key,title='Band',start='2027-10-25 20:00:00',source='OrangePeelOfficial'):
  return dict(source_key=source+':'+key,source_name=source,source_event_id=key,source_url='https://example.com/'+key,venue_id='orange-peel',venue_as_reported='Orange Peel',title=title,performance_start=start,date_status='venue_confirmed' if source.endswith('Official') else 'source_listed',date_note='',performers=[dict(name=title,role='headliner',confidence=1)],artist_spotify_links={})
 def test_shared_support_is_not_same_bill(self):
  def show(title,names):return dict(title=title,venue_id='v',performance_start='2027-01-01 20:00',sources=[],headliners=[dict(display_name=n) for n in names])
  a=show('Alpha with Support',['Alpha','Support']);b=show('Beta with Support',['Beta','Support'])
  self.assertFalse(duplicate(a,b,[a,b]))
 def test_import_and_cleanup_share_doors_time_rule(self):
  with connect(self.db) as c:
   one=upsert_show(c,self.event('official'))
   other=upsert_show(c,self.event('provider',start='2027-10-25 20:30:00',source='Songkick'))
   self.assertEqual(one,other)
  self.assertEqual(cleanup_duplicates(self.db),[])
 def test_two_official_performances_survive(self):
  with connect(self.db) as c:
   one=upsert_show(c,self.event('early'));two=upsert_show(c,self.event('late',start='2027-10-25 23:00:00'))
   self.assertNotEqual(one,two)
  self.assertEqual(cleanup_duplicates(self.db),[])
 def test_large_calendar_drop_blocks_retirement(self):
  base=dict(venue_id='orange-peel',source_url='https://example.com',pages=1)
  self.assertTrue(observation(start(self.db),dict(base,event_keys=[str(i) for i in range(20)]),self.db))
  self.assertFalse(observation(start(self.db),dict(base,event_keys=['1','2']),self.db))
 def test_detail_series_without_guessing_band(self):
  self.assertEqual(inspect('<p>Each event showcases six artists. The lineup is revealed only when the show begins.</p>')['entity_kind'],'series')
  self.assertIsNone(inspect('<p>Three concerts on three nights by a band.</p>')['entity_kind'])
 def test_structured_performer_preferred(self):
  evidence=inspect('<script type="application/ld+json">{"@type":"MusicEvent","performer":{"name":"Yarn","@type":"MusicGroup"}}</script>')
  self.assertEqual(evidence['performers'][0]['name'],'Yarn')
 def test_comedy_from_explicit_detail(self):
  self.assertEqual(inspect('<p>A comedian with fifteen years of stand-up experience.</p>')['category'],'comedy')
 def test_official_reappearance_overrules_stale_provider_cancellation(self):
  from concert_discovery.discovery import get_shows
  with connect(self.db) as c:
   e=self.event('provider',source='Songkick');e['event_status']='cancelled';upsert_show(c,e)
   e=self.event('official');e['event_status']='scheduled';upsert_show(c,e)
  self.assertEqual(len(get_shows(self.db)),1)
 def test_soft_merge_preserves_latest_status_and_history(self):
  from concert_discovery.reconciliation import schema
  with connect(self.db) as c:
   a=upsert_show(c,self.event('a'));b=upsert_show(c,self.event('b',title='Different bill',source='Songkick'))
   c.execute("UPDATE shows SET title='Band' WHERE show_id=?",(b,))
   c.execute('INSERT INTO user_show_decisions VALUES(?,?,?,?)',('user',a,'passed','2026-01-01'))
   c.execute('INSERT INTO user_show_decisions VALUES(?,?,?,?)',('user',b,'interested','2026-02-01'))
  self.assertEqual(len(cleanup_duplicates(self.db)),1)
  with connect(self.db) as c:
   self.assertEqual(c.execute('SELECT count(*) FROM shows').fetchone()[0],2)
   self.assertEqual(c.execute('SELECT decision FROM user_show_decisions WHERE user_id=? AND show_id=?',('user',a)).fetchone()[0],'interested')
   self.assertEqual(c.execute('SELECT count(*) FROM show_aliases').fetchone()[0],1)

 def test_existing_profile_alias_preserves_original_record(self):
  from concert_discovery.storage import upsert_artist
  from concert_discovery.spotify_matching import remember_source_identity
  with connect(self.db) as c:
   owner=upsert_artist(c,'Lead Artist','A'*22)
   alias=upsert_artist(c,'Lead Artist and Their Band')
  p=remember_source_identity({'artist_id':alias,'display_name':'Lead Artist and Their Band'},dict(spotify_artist_id='A'*22,name='Lead Artist',source_url='https://open.spotify.com/artist/'+'A'*22),'https://example.com/artist','Explicit linked profile',self.db)
  self.assertEqual(p['canonical_artist_id'],owner)
  with connect(self.db) as c:
   self.assertEqual(upsert_artist(c,'Lead Artist and Their Band'),owner)
   self.assertIsNotNone(c.execute('SELECT artist_id FROM artists WHERE artist_id=?',(alias,)).fetchone())
 def test_case_only_source_changes_keep_existing_title(self):
  with connect(self.db) as c:
   sid=upsert_show(c,self.event('one',title='Mixed Case'))
   upsert_show(c,self.event('one',title='MIXED CASE'))
   self.assertEqual(c.execute('SELECT title FROM shows WHERE show_id=?',(sid,)).fetchone()[0],'Mixed Case')
