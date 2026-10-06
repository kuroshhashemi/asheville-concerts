import unittest
from concert_discovery.event_classification import classify,CATEGORY_LABELS,EXCLUDED
class CategoryTests(unittest.TestCase):
 def test_categories(self):
  for title,expected in [('Goth Prom','events'),('Blue Country Line Dance’s Giddy Up Brunch','events'),('TERRAOKE | Free Karaoke Night!','events'),('DARK FREAKQUENCIES - A Gothic Dance Night - HALLOWEEN EDITION','events'),('25th Annual NewSong Music Competition','events'),('Burlesque','events'),('Golden Folk Sessions','events'),('Shakedown Sunday’s','events'),('A Magical Cirque Christmas','events'),('Rumours ATL: A Fleetwood Mac Tribute','cover_band'),('Zoso – The Ultimate Led Zeppelin Experience','cover_band'),('Michael Shannon & Jason Narducy and Friends play R.E.M.’s Document','cover_band'),('Stand-up comedy','comedy'),('Volleyball Championships','sports'),('Dance Competition','dance'),('Ballet','dance'),('Theatre performance','theatre')]:
   self.assertEqual(classify(title)[0],expected,title)
 def test_default_and_retained_events(self):
  self.assertEqual(CATEGORY_LABELS[classify('An unfamiliar performer')[0]],'live_music')
  self.assertEqual(EXCLUDED,set())

class DetailEvidenceTests(unittest.TestCase):
 def test_event_types_and_footer_isolation(self):
  from concert_discovery.bill_evidence import inspect
  self.assertEqual(inspect('<h1>A performer</h1><p>A concert tonight.</p><footer><p>Comedy and volleyball listings</p></footer>')['category'],'unknown')
  self.assertEqual(inspect('<h1>An evening</h1><script type="application/ld+json">{"@type":"ComedyEvent","name":"An evening"}</script>')['category'],'comedy')
  self.assertEqual(inspect('<h1>Goth Prom</h1>')['category'],'events')
 def test_research_saves_category_without_altering_bill(self):
  import sqlite3
  from concert_discovery.bill_evidence import save
  c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
  c.execute('CREATE TABLE show_sources(show_id INTEGER,source_key TEXT)');c.execute("INSERT INTO show_sources VALUES(1,'TestOfficial:1')")
  save(c,dict(source_key='TestOfficial:1',source_url='https://example.com/event',title='A performer'),dict(category='comedy',evidence='Explicit comedian bio',performers=[]))
  self.assertEqual(c.execute('SELECT category FROM show_classifications').fetchone()[0],'comedy')

class PresentationAndRecurrenceTests(unittest.TestCase):
 def test_duplicate_project_names_preserve_verified_profile(self):
  from concert_discovery.bill_presentation import performers
  for first,second in [('Grahame Lesh','Grahame Lesh & Friends'),('Zoso','Zoso – The Ultimate Led Zeppelin Experience')]:
   artists=[dict(display_name=first,spotify_artist_id='one'),dict(display_name=second,spotify_artist_id=None)]
   result=performers(artists,second)
   self.assertEqual(len(result),1);self.assertEqual(result[0]['spotify_artist_id'],'one')
  conflict=[dict(display_name='Grahame Lesh',spotify_artist_id='one'),dict(display_name='Grahame Lesh & Friends',spotify_artist_id='two')]
  self.assertEqual(len(performers(conflict,'')),2)
 def test_event_title_is_not_truncated(self):
  from concert_discovery.bill_presentation import name
  title='THE MOTH Presents: Asheville StorySLAM – MAGIC'
  self.assertEqual(name(dict(title=title,event_classification={'category':'events'},headliners=[{'display_name':'THE MOTH Presents'}])),title)
 def test_recurring_events_only(self):
  from concert_discovery.recurring_events import exclusions
  def rows(kind,dates):return [dict(show_id=i,title='Same Series',venue_id='v',performance_start=d,event_classification={'category':kind}) for i,d in enumerate(dates)]
  dates=['2026-10-01','2026-10-08','2026-10-15']
  self.assertEqual(len(exclusions(rows('events',dates))),3)
  self.assertFalse(exclusions(rows('live_music',dates)))
  self.assertFalse(exclusions(rows('cover_band',dates)))
  self.assertFalse(exclusions(rows('events',['2026-10-01','2026-10-02','2026-10-03'])))
 def test_presenter_prefix_is_shared(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual(parse_performers('Live Nation Presents: Hudson Westbrook – The Hits Me Tour')[0]['name'],'Hudson Westbrook')

class ExplicitRecurringTests(unittest.TestCase):
 def test_verified_series_stays_hidden_with_only_one_future_date(self):
  from concert_discovery.recurring_events import exclusions
  show=dict(show_id=1,title='A showcase',venue_id='v',performance_start='2026-12-01',event_classification={'category':'events','recurring_series':True,'evidence':'Official recurring showcase description'})
  self.assertIn(1,exclusions([show]))

class ExclusionLabelsTests(unittest.TestCase):
 def test_short_reason_labels(self):
  from concert_discovery.discovery import exclusion_label
  for reason,label in [('Duplicate listing merged into another show','Duplicate'),('Absent from two complete official-calendar checks','No longer listed'),('Recurring Events series: 3 dates across 56 days','Recurring event'),('Explicitly identified recurring Events series: source description','Recurring event')]:self.assertEqual(exclusion_label(reason),label)
 def test_boot_scootin_format_from_description(self):
  from concert_discovery.bill_evidence import inspect
  result=inspect('<h1>Boot Scootin’ Boogie Nights</h1><p>A party hosted by a collective of musicians for a night of line dancing.</p>')
  self.assertEqual(result['category'],'events')
 def test_structured_tribute_metadata_at_import(self):
  from concert_discovery.event_classification import classify
  self.assertEqual(classify('Unfamiliar act',[{'segment':{'name':'Music'},'genre':{'name':'Tribute'}}])[0],'cover_band')
