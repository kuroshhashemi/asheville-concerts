import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from concert_discovery.storage import initialize,connect
from concert_discovery.venue_artwork import refresh,saved_icons

class VenueArtworkTests(unittest.TestCase):
 def test_new_venue_icon_discovered_and_reused(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'db';initialize(db)
   with connect(db) as c:
    c.execute('DELETE FROM venue_icons');c.execute('DELETE FROM venues')
    c.execute("INSERT INTO venues(venue_id,name,official_url,feed_alias,coverage_note) VALUES('test','Test','https://example.com/','test','test')")
   page=Mock(text='<link rel="icon" href="/brand.png">',url='https://example.com/')
   icon=Mock(ok=True,content=b'image',headers={'Content-Type':'image/png'})
   with patch('concert_discovery.venue_artwork.requests.get',side_effect=[page,icon]) as get:
    refresh(db);refresh(db);self.assertEqual(get.call_count,2)
   with connect(db) as c:self.assertEqual(c.execute("SELECT icon_url FROM venue_icons WHERE venue_id='test'").fetchone()[0],'https://example.com/brand.png')
 def test_revival_shared_icon(self):self.assertTrue(saved_icons()['revival'].startswith('data:image/webp;base64,'))
