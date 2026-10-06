from test_matching_queue import QueueTests
from concert_discovery.discovery import get_shows
from concert_discovery.refresh import save_events
from concert_discovery.storage import connect
class AnnouncementTests(QueueTests):
 def test_initial_import_is_baseline_and_later_new_show_expires(self):
  self.assertFalse(get_shows(self.db)[0]['just_announced'])
  new=dict(self.e,title='New Artist',source_key='new',source_url='https://example.com/new',performers=[{'name':'New Artist','role':'headliner','confidence':1}])
  save_events([new],self.db)
  row=next(s for s in get_shows(self.db) if s['title']=='New Artist')
  self.assertTrue(row['just_announced'])
  with connect(self.db) as c:c.execute("UPDATE show_discovery SET first_seen_at='2000-01-01'")
  self.assertFalse(next(s for s in get_shows(self.db) if s['title']=='New Artist')['just_announced'])
