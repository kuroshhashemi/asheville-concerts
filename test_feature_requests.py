import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from concert_discovery.feature_requests import request_message,submit
class RequestTests(unittest.TestCase):
 def test_owner_only(self):
  msg=request_message({'email':'visitor@example.com','name':'Visitor'},'Add a date filter\nBcc: evil@example.com','owner@example.com',datetime(2026,10,15,tzinfo=timezone.utc))
  self.assertEqual(msg['To'],'owner@example.com');self.assertIsNone(msg['Bcc'])
  self.assertIn('visitor@example.com',msg.get_content());self.assertIn('2026-10-15',msg.get_content())
 def test_validation(self):
  for user,text in [({},'Some request'),({'email':'a@b.c'},' '),({'email':'a@b.c'},'a'*4001),({'email':'a@b.c','email_verified':False},'Some request')]:
   with self.assertRaises(ValueError):request_message(user,text,'owner@example.com')
 def test_send(self):
  with patch('concert_discovery.feature_requests.smtplib.SMTP_SSL') as smtp:
   submit({'email':'visitor@example.com'},'A useful request','owner@example.com','password')
   self.assertEqual(smtp.return_value.__enter__.return_value.send_message.call_count,1)
