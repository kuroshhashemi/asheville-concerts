import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from concert_discovery.storage import initialize,connect
from concert_discovery.operations_alerts import readable_report
class ReadableAlertTests(unittest.TestCase):
 def test_show_names_saved_prices_and_retry_without_internal_identifiers(self):
  from concert_discovery.api_sources import event
  from concert_discovery.refresh import save_events
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'db.sqlite3';initialize(db)
   e=event('OrangePeelOfficial','https://example.com/show','Cory Wong','2027-02-24','orange-peel',[{'name':'Cory Wong','role':'headliner','confidence':1}]);e['ticket_url']='https://www.etix.com/ticket/p/94389193/cory-wong';save_events([e],db)
   with connect(db) as c:key=c.execute('SELECT dedupe_key FROM shows').fetchone()[0]
   problem=dict(entity_type='show',entity_key=key,field='tickets',status='blocked',detail='blocked_or_unavailable',checked_at='2026-10-20T10:17:00+00:00',next_attempt_at='2026-10-21T10:17:00+00:00')
   with patch('concert_discovery.prices.load',return_value={'etix.com/ticket/p/94389193/cory-wong':{'min':45,'max':60}}):
    text=readable_report([problem],db,datetime(2026,10,20,12,tzinfo=timezone.utc))
   self.assertIn('Cory Wong',text);self.assertIn('Orange Peel',text);self.assertIn('Feb 24, 2027',text)
   self.assertIn('Saved price: $45+',text);self.assertIn('Eligible after',text)
   self.assertNotIn('entity_key',text);self.assertNotIn('blocked_or_unavailable',text);self.assertNotIn(key,text)
   self.assertIn('does not establish the exact cause',text)
 def test_missing_context_remains_readable(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'db.sqlite3'
   row=dict(entity_type='artist',entity_key='internal-id',field='growth',status='pending',detail='',checked_at=None,next_attempt_at=None)
   with patch('concert_discovery.prices.load',return_value={}):text=readable_report([row],db,datetime.now(timezone.utc))
   self.assertIn('Six-month listener growth',text);self.assertIn('Not attempted yet',text);self.assertNotIn('internal-id',text)
