import unittest
from datetime import date
from concert_discovery.eulogy_calendar import parse_event
class EulogyCalendarTests(unittest.TestCase):
 def test_night_identity_and_timezone(self):
  e={'name':'PROJECT PAT - NIGHT 2','url':'https://example.com','venues':[{'name':'Eulogy'}],'date':'2026-10-18T00:00:00Z','timezone':'America/New_York','ticket_types':[{'sold_out':True}]}
  r=parse_event(e,date(2026,10,1));self.assertEqual(r['performance_start'],'2026-10-17 20:00:00');self.assertEqual(r['performers'][0]['name'],'PROJECT PAT');self.assertEqual(r['ticket_availability'],'sold_out')
  e['is_multi_days_event']=True;self.assertIsNone(parse_event(e,date(2026,10,1)))

class Response:
 def __init__(self,data=None,text='',fail=False):self.data=data;self.text=text;self.fail=fail
 def raise_for_status(self):
  if self.fail:raise RuntimeError('fetch failed')
 def json(self):return self.data
class Session:
 def __init__(self,responses):self.responses=iter(responses);self.calls=0
 def get(self,*a,**kw):self.calls+=1;return next(self.responses)
class PaginationTests(unittest.TestCase):
 def test_follows_next_to_end_and_reports_complete(self):
  from concert_discovery.eulogy_calendar import fetch_eulogy
  html='DiceEventListWidget.create({"apiKey":"public-test-key","promoters":["test"]});'
  def item(name,day):return {'name':name,'date':day+'T01:00:00Z','url':'https://example.com/'+name,'venues':[{'name':'Eulogy'}]}
  session=Session([Response(text=html),Response({'data':[item('First','2026-11-01')],'links':{'next':'https://events-api.dice.fm/api/v2/events?page[number]=2'}}),Response({'data':[item('Later','2026-11-29')],'links':{'next':None}})])
  rows,snapshot=fetch_eulogy(session,date(2026,10,1));self.assertEqual(len(rows),2);self.assertTrue(snapshot['complete']);self.assertEqual(snapshot['pages'],2);self.assertEqual(session.calls,3)
 def test_page_failure_never_returns_complete_snapshot(self):
  from concert_discovery.eulogy_calendar import fetch_eulogy
  session=Session([Response(text='DiceEventListWidget.create({"apiKey":"public-test-key","promoters":["test"]});'),Response({'data':[],'links':{'next':'https://events-api.dice.fm/api/v2/events?page[number]=2'}}),Response(fail=True)])
  with self.assertRaises(RuntimeError):fetch_eulogy(session,date(2026,10,1))

class MetadataConsistencyTests(unittest.TestCase):
 def test_billing_spelling_wins_over_near_identical_metadata(self):
  e={'name':'Noah Gundersen: Rites of Spring US TOUR FALL 2026','artists':['Noah Gunderson'],'url':'https://example.com','venues':[{'name':'Eulogy'}],'date':'2026-10-15T23:00:00Z'}
  self.assertEqual(parse_event(e,date(2026,10,1))['performers'][0]['name'],'Noah Gundersen')
 def test_tour_suffix_does_not_become_artist_identity(self):
  e={'name':"Rickshaw Billie's Burger Patrol - Ca$h Grab Tour",'artists':[" Rickshaw Billie's Burger Patrol"],'url':'https://example.com','venues':[{'name':'Eulogy'}],'date':'2026-12-13T01:00:00Z'}
  self.assertEqual(parse_event(e,date(2026,10,1))['performers'][0]['name'],"Rickshaw Billie's Burger Patrol")

class LiveScoreTests(unittest.TestCase):
 def test_film_title_is_not_artist(self):
  e={"name":"FAUST with live metal score", "url":"https://example.com", "venues":[{"name":"Eulogy"}], "date":"2026-10-09T00:00:00Z", "timezone":"America/New_York", "raw_description":"A film accompanied by a haunting live metal score performed by The Silent Light. One night only."}
  r=parse_event(e,date(2026,10,1));self.assertEqual([a["name"] for a in r["performers"]],["The Silent Light"])
