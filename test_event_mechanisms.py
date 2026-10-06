import unittest,tempfile
from pathlib import Path
from datetime import date
from concert_discovery.event_classification import classify
from concert_discovery.official_calendar import parse_calendar
from concert_discovery.storage import initialize,connect,upsert_show
from concert_discovery.reconciliation import same_bill
class MechanismTests(unittest.TestCase):
 def test_explicit_sports_subtitle_and_comedy(self):
  self.assertEqual(classify("The Gala January 8-10 Women's Gymnastics Competition")[0],'sports')
  self.assertEqual(classify('Someone', [{'segment':{'name':'Arts & Theatre'},'genre':{'name':'Comedy'}}])[0],'comedy')
  self.assertEqual(classify('The Gala')[0],'events')
 def card(self,name='Band',date_text='Sun, Oct 25',room='The Orange Peel'):
  return f'<div class="eventWrapper"><a id="eventTitle" href="https://example.com/show">{name}</a><div id="eventDate">{date_text}</div><a class="venueLink">{room}</a></div>'
 def test_cancelled_events_are_saved_as_evidence(self):
  rows=parse_calendar(self.card('*CANCELLED* Band'),date(2026,10,5))
  self.assertEqual(rows[0]['event_status'],'cancelled')
 def test_pulp_is_recognized_separately(self):
  self.assertEqual(parse_calendar(self.card(room='Pulp'),date(2026,10,5))[0]['venue_id'],'pulp')
 def test_source_identity_corrects_year_without_creating_new_show(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'data.db';initialize(db)
   e=parse_calendar(self.card(),date(2026,10,5))[0]
   with connect(db) as c:
    old=dict(e,performance_start='2027-10-25');a=upsert_show(c,old);b=upsert_show(c,e)
    self.assertEqual(a,b);self.assertEqual(c.execute('SELECT performance_start FROM shows').fetchone()[0],'2026-10-25')
 def test_project_suffix_not_different_band(self):
  self.assertTrue(same_bill('Grahame Lesh & Friends','Grahame Lesh'))
  self.assertFalse(same_bill('Grahame Lesh & Other Band','Grahame Lesh'))
 def test_bill_order_matches_title(self):
  from concert_discovery.discovery import get_shows
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'data.db';initialize(db)
   e=parse_calendar(self.card('Zebra & Apple'),date(2026,10,5))[0]
   e['performers']=[dict(name=n,role='headliner',confidence=1) for n in ['Zebra','Apple']]
   with connect(db) as c:upsert_show(c,e)
   self.assertEqual([a['display_name'] for a in get_shows(db)[0]['headliners']],['Zebra','Apple'])

class SierraTests(unittest.TestCase):
 def test_uppercase_dates_location_and_time(self):
  from concert_discovery.sierra_calendar import parse_cards
  rows=parse_cards([dict(title='Late Shifters',url='https://example.com/a',text='OCTOBER 10\nAMPHITHEATER|MILLS RIVER\n2:00 PM - 5:00 PM'),dict(title='Chico show',url='https://example.com/b',text='October 10 Big Room|Chico')],date(2026,10,5))
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['performance_start'],'2026-10-10 14:00:00')
 def test_unparsed_local_card_disables_complete_snapshot(self):
  from concert_discovery.sierra_calendar import parse_cards
  with self.assertRaises(ValueError):parse_cards([dict(title='Band',url='url',text='Mills River no date')])

class ClassificationDisplayTests(unittest.TestCase):
 def test_sports_and_comedy_kept_and_cancellation_cleared_on_reappearance(self):
  from concert_discovery.discovery import get_shows
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'data.db';initialize(db)
   for title,label in [('Gala','Gymnastics competition'),('A performer','Comedy show')]:
    e=parse_calendar(MechanismTests().card(title),date(2026,10,5))[0]
    e['source_key']+=title;e['ticket_url']=None;e['category_text']=label
    with connect(db) as c:upsert_show(c,e)
   self.assertEqual({s['title'] for s in get_shows(db)},{'Gala','A performer'})
   e['event_status']='cancelled'
   with connect(db) as c:upsert_show(c,e)
   self.assertEqual([s['title'] for s in get_shows(db)],['Gala'])
   e['event_status']='scheduled'
   with connect(db) as c:upsert_show(c,e)
   self.assertEqual(len(get_shows(db)),2)
