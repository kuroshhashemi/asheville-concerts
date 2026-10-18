import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from concert_discovery.storage import connect
from concert_discovery.metadata_outcomes import record
from concert_discovery.operations_alerts import check

class OutcomeTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.db=Path(t.name)/'db.sqlite3';self.now=datetime(2026,10,18,tzinfo=timezone.utc)
 def put(self,status,checked,now):
  with connect(self.db) as c:record(c,'artist','example','growth',status,checked,detail='Test outcome',now=now.isoformat())
 def test_replaying_same_failed_attempt_does_not_inflate_failure_count(self):
  self.put('blocked',self.now.isoformat(),self.now);self.put('blocked',self.now.isoformat(),self.now+timedelta(days=2))
  with connect(self.db) as c:self.assertEqual(c.execute('SELECT consecutive_failures FROM metadata_outcomes').fetchone()[0],1)
  with patch('concert_discovery.operations_alerts.notify') as send:check(self.db,now=self.now+timedelta(days=2));send.assert_not_called()
 def test_persistent_failure_alerts_and_success_clears_failure(self):
  self.put('blocked',self.now.isoformat(),self.now)
  later=self.now+timedelta(days=2);self.put('blocked',later.isoformat(),later)
  with patch('concert_discovery.operations_alerts.notify',return_value={'sent':True}) as send:check(self.db,now=later);send.assert_called_once()
  self.put('complete',later.isoformat(),later)
  with connect(self.db) as c:
   r=c.execute('SELECT * FROM metadata_outcomes').fetchone();self.assertEqual(r['consecutive_failures'],0);self.assertIsNone(r['first_failure_at'])
 def test_unavailable_and_waiting_for_identity_do_not_alert(self):
  for state in ('unavailable','not_applicable','unresolved','waiting_for_identity'):
   self.put(state,None,self.now)
   with patch('concert_discovery.operations_alerts.notify') as send:check(self.db,now=self.now+timedelta(days=10));send.assert_not_called()
 def test_alerts_only_owner_and_deduplicate(self):
  from concert_discovery.operations_alerts import notify
  with patch.dict('os.environ',{'EMAIL_SENDER':'owner@example.com','EMAIL_APP_PASSWORD':'test'}),patch('concert_discovery.operations_alerts.smtplib.SMTP_SSL') as smtp:
   self.assertEqual(notify('digest-held','Example held digest',self.db,self.now)['operations_alert'],'sent_to_owner')
   self.assertEqual(notify('digest-held','Example held digest',self.db,self.now+timedelta(days=2))['operations_alert'],'unchanged_or_throttled')
   msg=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
   self.assertEqual(msg['To'],'owner@example.com');smtp.assert_called_once()
 def test_failed_alert_not_recorded_as_sent(self):
  from concert_discovery.operations_alerts import notify
  with patch.dict('os.environ',{'EMAIL_SENDER':'owner@example.com','EMAIL_APP_PASSWORD':'test'}),patch('concert_discovery.operations_alerts.smtplib.SMTP_SSL',side_effect=OSError):
   self.assertEqual(notify('digest-held','Test',self.db,self.now)['operations_alert'],'send_failed')
  with connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM operations_alerts').fetchone()[0],0)
 def test_admin_guard_no_reads_for_other_users(self):
  from concert_discovery.metadata_outcomes import admin_view
  with patch('concert_discovery.metadata_outcomes.connect') as read:
   admin_view(None,{'email':'friend@example.com'},'owner@example.com',self.db);read.assert_not_called()
