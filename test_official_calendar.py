import unittest
from datetime import date
from concert_discovery.official_calendar import parse_calendar
class OfficialTests(unittest.TestCase):
 def test_explicit_venue_year_and_duplicate_layout(self):
  event='''<div class="eventWrapper"><div id="eventDate">Fri, Oct 30</div><a id="eventTitle" href="https://example.com/show">Wednesday &amp; Mannequin Pussy</a><h4 id="evSubHead"><a>Snõõper</a></h4><span>Show: 7 pm | Doors: 6 pm</span><a class="venueLink">Hellbender</a><a href="https://www.etix.com/ticket/p/123">Tickets</a></div>'''
  es=parse_calendar('<span class="rhp-events-list-separator-month">October 2026</span>'+event+event,date(2026,10,1))
  self.assertEqual(len(es),1); self.assertEqual(es[0]['venue_id'],'hellbender');self.assertEqual(es[0]['performance_start'],'2026-10-30 19:00:00')
  self.assertIn('Snõõper',[p['name'] for p in es[0]['performers']])

 def test_year_does_not_leak_between_desktop_mobile_layouts(self):
  def card(name,weekday,month,day):
   return f'<div class="eventWrapper"><span id="eventDate">{weekday}, {month} {day}</span><a id="eventTitle" href="https://example.com/{name}">{name}</a><a class="venueLink">The Orange Peel</a></div>'
  html='<section><span class="rhp-events-list-separator-month">April 2027</span>'+card('Future','Thu','Apr',22)+'</section><section>'+card('Cannons','Tue','Oct',13)+'</section>'
  rows=parse_calendar(html,date(2026,10,4))
  self.assertEqual(next(r for r in rows if r['title']=='Cannons')['performance_start'],'2026-10-13')
  self.assertEqual(next(r for r in rows if r['title']=='Future')['performance_start'],'2027-04-22')
 def test_contradictory_weekday_is_not_saved(self):
  html='<span class="rhp-events-list-separator-month">October 2027</span><div class="eventWrapper"><span id="eventDate">Tue, Oct 13</span><a id="eventTitle" href="https://example.com/cannons">Cannons</a><a class="venueLink">The Orange Peel</a></div>'
  with self.assertRaises(ValueError):parse_calendar(html,date(2026,10,4))

class HarrahStatusPrefixTests(unittest.TestCase):
 def test_scheduling_prefix_is_not_a_performer(self):
  from concert_discovery.official_calendar import parse_harrah
  for prefix in ('RESCHEDULED: ', 'POSTPONED — ', 'CANCELLED: '):
   title=prefix+'Daniel Tosh: My First Farewell Tour'
   html=f'<div class="event-wrap_feed"><h3><a href="https://www.harrahscherokeecenterasheville.com/events/2026-daniel-tosh/">{title}</a></h3><div class="event-date">Oct 16</div><div class="event-venue">Thomas Wolfe Auditorium</div></div>'
   row=parse_harrah(html,date(2026,10,6))[0]
   self.assertEqual(row['title'],title)
   self.assertEqual([p['name'] for p in row['performers']],['Daniel Tosh'])

class HarrahSharedVenueTests(unittest.TestCase):
 def test_missing_room_is_still_a_harrah_event_and_snapshot_covers_both_rooms(self):
  from unittest.mock import patch,Mock
  from concert_discovery.official_calendar import parse_harrah,fetch_all_calendars
  html='<div class="event-wrap_feed"><h3><a href="https://www.harrahscherokeecenterasheville.com/events/2099-example/">Example Band</a></h3><div class="event-date">Apr 13</div></div>'
  row=parse_harrah(html,date(2098,11,17))[0]
  self.assertEqual(row['venue_id'],'harrahs-arena')
  self.assertEqual(row['venue_as_reported'],"Harrah's")
  response=Mock(text=html)
  snapshots=[]
  with patch('concert_discovery.official_calendar.CALENDARS',[('HarrahOfficial','https://www.harrahscherokeecenterasheville.com/events-tickets/','harrah')]),patch('concert_discovery.official_calendar.requests.get',return_value=response):
   events,errors=fetch_all_calendars(snapshots=snapshots)
  self.assertEqual(errors,[])
  self.assertEqual({s['venue_id'] for s in snapshots},{'harrahs-arena','thomas-wolfe'})
  self.assertTrue(all(s['event_keys']==[events[0]['source_key']] for s in snapshots))
