import unittest,tempfile
from pathlib import Path
from concert_discovery.ticket_destinations import identity,collect,resolve,event_page
from concert_discovery.storage import initialize,connect
class DestinationTests(unittest.TestCase):
 def test_official_card_repairs_only_matching_date_and_preserves_total(self):
  from unittest.mock import patch
  from concert_discovery.prices import url_key
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'catalog.sqlite3';initialize(db)
   with connect(db) as c:
    vid=c.execute("SELECT venue_id FROM venues WHERE name='Third Room'").fetchone()[0]
    for day in ('2026-10-31','2026-11-01'):
     c.execute('INSERT INTO shows(dedupe_key,venue_calendar_url,venue_id,title,performance_start,ticket_url,date_status,last_seen_at) VALUES(?,?,?,?,?,?,?,?)',(day,'https://thirdroom.art/',vid,'Example Band at Third Room',day,'https://thirdroom.art/','scheduled',day))
   dest='https://wl.eventim.us/event/example/123456'
   html='<div class="seetickets-list-event-container"><p class="headliners">Example Band</p><p class="date">Sat Oct 31</p><span class="price">$20-$25</span><a href="'+dest+'">Tickets</a></div>'
   with patch('concert_discovery.prices.load',return_value={url_key(dest):{'min':30,'max':30}}),patch('concert_discovery.prices.save') as saved:
    collect(html,'https://thirdroom.art/',db);saved.assert_not_called()
   with connect(db) as c:
    rows=c.execute('SELECT ticket_url FROM shows ORDER BY performance_start').fetchall()
    self.assertEqual(rows[0][0],dest);self.assertEqual(rows[1][0],'https://thirdroom.art/')
 def test_brevard_ticket_link_ignores_global_buy_navigation(self):
  from unittest.mock import patch
  markup='<a href="https://www.brevardmusic.org/events/">Buy Tickets</a><a href="https://secured.brevardmusic.org/1947/1954">Purchase Tickets</a>'
  with patch('concert_discovery.ticket_destinations.connect') as mocked:
   mocked.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[{'show_id':1}]
   event_page(markup,'https://www.brevardmusic.org/event/django/')
   self.assertEqual(mocked.return_value.__enter__.return_value.execute.call_args[0][1][0],'https://secured.brevardmusic.org/1947/1954')
 def test_generic_refresh_cannot_replace_verified_event_link(self):
  from concert_discovery.ticket_destinations import retain_verified_link,schema
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'catalog.sqlite3';initialize(db)
   with connect(db) as c:
    schema(c);c.execute('INSERT INTO official_ticket_links VALUES(?,?,?,?)',(1,'https://secured.brevardmusic.org/1947/1954','https://www.brevardmusic.org/event/django/','2026-10-14'))
    self.assertEqual(retain_verified_link(c,1,'https://www.brevardmusic.org/events/'),'https://secured.brevardmusic.org/1947/1954')
    self.assertEqual(retain_verified_link(c,1,'https://secured.brevardmusic.org/1947/9999'),'https://secured.brevardmusic.org/1947/9999')
 def test_vendor_identity_not_artist_name(self):
  self.assertEqual(identity('https://prod-nts-api.seeticketsusa.us/v1.0.0/promote/YWZmOlNUVVMtNzA1Mzc4OjE4/clickthru'),'705378')
  self.assertEqual(identity('https://wl.eventim.us/event/anything/705378'),'705378')
  self.assertIsNone(identity('https://example.com/event/705378'))
 def test_etix_affiliate_destination_is_safe_and_reusable(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'catalog.sqlite3';initialize(db)
   with connect(db) as c:
    self.assertEqual(resolve(c,'https://etix.prf.hn/click/camref:x/destination:https://www.etix.com/ticket/p/54321160/band?utm_source=jambase'),'https://www.etix.com/ticket/p/54321160/band')
    unsafe='https://etix.prf.hn/click/destination:https://evil.example/p/54321160'
    self.assertEqual(resolve(c,unsafe),unsafe)
 def test_verified_link_survives_resolving_legacy_clickthrough(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'catalog.sqlite3';initialize(db)
   collect('<a href="https://wl.seetickets.us/event/saturna/705378">Tickets</a>','https://thirdroom.art/',db)
   with connect(db) as c:
    self.assertEqual(resolve(c,'https://prod-nts-api.seeticketsusa.us/v1.0.0/promote/YWZmOlNUVVMtNzA1Mzc4OjE4/clickthru'),'https://wl.eventim.us/event/saturna/705378')
