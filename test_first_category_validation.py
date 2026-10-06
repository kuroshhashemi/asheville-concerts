import unittest,tempfile,sqlite3
from pathlib import Path
from unittest.mock import patch,Mock
from concert_discovery.bill_evidence import enrich_events

class FirstValidationTests(unittest.TestCase):
 def test_all_new_pages_checked_and_shared_urls_cached(self):
  with tempfile.TemporaryDirectory() as directory:
   db=Path(directory)/'test.sqlite3'
   with sqlite3.connect(db) as c:c.execute('CREATE TABLE show_sources(show_id INTEGER,source_key TEXT)')
   events=[dict(source_key=f'TestOfficial:{i}',source_url=f'https://example.com/event/{i}',source_name='TestOfficial',title=f'Act {i}') for i in range(12)]
   events.append(dict(events[0],source_key='AnotherSource:0'))
   response=Mock(text='<h1>A live act</h1><p>An evening with musicians.</p>');response.raise_for_status.return_value=None
   with patch('concert_discovery.bill_evidence.requests.get',return_value=response) as get:
    self.assertEqual(enrich_events(events,db),12)
    self.assertEqual(get.call_count,12)
    self.assertEqual(enrich_events(events,db),0)
    self.assertEqual(get.call_count,12)
    # A different source key for the same URL can reuse the saved description.
    self.assertEqual(enrich_events([dict(events[0],source_key='ThirdSource:0')],db),0)
    self.assertEqual(get.call_count,12)
   with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT count(*) FROM bill_evidence').fetchone()[0],14)
 def test_failed_pages_are_not_retried_on_each_refresh(self):
  import requests
  with tempfile.TemporaryDirectory() as directory:
   db=Path(directory)/'test.sqlite3'
   with sqlite3.connect(db) as c:c.execute('CREATE TABLE show_sources(show_id INTEGER,source_key TEXT)')
   e=dict(source_key='TestOfficial:1',source_url='https://example.com/event',source_name='TestOfficial',title='Unknown act')
   with patch('concert_discovery.bill_evidence.requests.get',side_effect=requests.Timeout) as get:
    self.assertEqual(enrich_events([e],db),1)
    self.assertEqual(enrich_events([e],db),0)
    self.assertEqual(get.call_count,1)
   with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT state FROM bill_evidence').fetchone()[0],'failed')
