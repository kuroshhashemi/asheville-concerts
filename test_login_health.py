import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
from concert_discovery.login_health import concerns,attempt_key,LoginStore,admin_view
from concert_discovery.auth_monitor import monitor
class LoginHealthTests(unittest.TestCase):
 def setUp(self):self.now=datetime.now(timezone.utc)
 def row(self,status='started',minutes=45,**kw):return {'outcome':status,'started_at':(self.now-timedelta(minutes=minutes)).isoformat(),**kw}
 def test_abandoned_attempt_not_failure(self):self.assertEqual(concerns([self.row()],self.now),[])
 def test_incomplete_cluster_but_not_new_or_old_or_test_attempts(self):
  self.assertEqual(concerns([self.row() for _ in range(5)],self.now)[0][0],'login-incomplete')
  for row in (self.row(minutes=1),self.row(minutes=180),self.row(is_test=True)):
   self.assertEqual(concerns([row]*6,self.now),[])
 def test_errors_alert_and_success_does_not(self):
  self.assertEqual(concerns([self.row('error')],self.now)[0][0],'login-errors')
  self.assertEqual(concerns([self.row('success')],self.now),[])
 def test_identifier_validation(self):
  self.assertIsNone(attempt_key('raw-token-or-provider-error'))
 def test_owner_guard_prevents_all_reads(self):
  store=Mock();admin_view(Mock(),store,{'email':'other@example.com'},'owner@example.com');store.recent.assert_not_called()
 def test_finish_sanitizes_error_and_updates_only_pending_rows(self):
  store=LoginStore('https://example.com','secret');store.call=Mock(return_value=[])
  store.finish('12345678-1234-1234-1234-123456789012',error=True)
  call=store.call.call_args
  self.assertEqual(call.kwargs['json']['error_code'],'app_login_error')
  self.assertEqual(call.kwargs['params']['outcome'],'eq.started')
 def test_success_requires_verified_identity(self):
  store=LoginStore('https://example.com','secret');store.call=Mock()
  with self.assertRaises(ValueError):store.finish('12345678-1234-1234-1234-123456789012',{'email':'x','email_verified':False})
 def test_alert_throttled_and_failed_send_not_marked(self):
  store=Mock();store.recent.return_value=[self.row('error')];store.last_alert.return_value=None
  send=Mock(return_value={'operations_alert':'send_failed'})
  monitor(store,send,self.now);store.mark_alert.assert_not_called()
  send.return_value={'operations_alert':'sent_to_owner'};monitor(store,send,self.now);store.mark_alert.assert_called_once()
  store.last_alert.return_value=self.now.isoformat();send.reset_mock();monitor(store,send,self.now);send.assert_not_called()
 def test_monitor_reports_storage_failure(self):
  store=Mock();store.recent.side_effect=RuntimeError;send=Mock(return_value={})
  monitor(store,send,self.now);self.assertEqual(send.call_args.args[0],'login-storage-unavailable')
