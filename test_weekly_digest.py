import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, Mock
import smtplib
from concert_discovery.weekly_digest import monday_end, new_shows, render, run, send_email
from concert_discovery.email_store import EmailStore

UTC = timezone.utc
END = datetime(2026, 10, 19, 13, tzinfo=UTC)


class FakeStore:
    def __init__(self):
        self.subscription = {'subscription_id': 'private-id', 'email': 'person@example.com', 'enabled': True,
                             'subscribed_at': '2026-10-10T00:00:00+00:00', 'last_processed_at': None,
                             'unsubscribe_token': 'a' * 43}
        self.claimed = {}; self.finished = []; self.active = True
    def enabled(self): return [self.subscription]
    def sent_keys(self, sid): return set()
    def claim(self, sid, end, keys):
        if (sid, end) in self.claimed: return False
        self.claimed[(sid, end)] = keys
        return True
    def is_enabled(self, sid): return self.active
    def finish(self, sid, end, status, mid=None):
        self.finished.append(status)
        if status in ('sent', 'empty'): self.subscription['last_processed_at'] = end


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'db.sqlite3'
        self.db.touch()
        self.db.with_name('freshness.json').write_text(json.dumps({'refreshed_at': END.isoformat()}))
    def tearDown(self): self.temp.cleanup()

    def test_start_date_and_daylight_saving(self):
        self.assertIsNone(monday_end(datetime(2026, 10, 12, 14, tzinfo=UTC)))
        self.assertIsNone(monday_end(END - timedelta(minutes=1)))
        self.assertEqual(monday_end(END + timedelta(hours=3)), END)
        self.assertIsNone(monday_end(END + timedelta(days=1)))
        self.assertIsNone(monday_end(datetime(2026, 11, 2, 13, 17, tzinfo=UTC)))
        self.assertEqual(monday_end(datetime(2026, 11, 2, 14, 17, tzinfo=UTC)), datetime(2026, 11, 2, 14, tzinfo=UTC))

    def test_new_window_baseline_and_already_sent_aliases(self):
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE show_discovery(show_id INTEGER,first_seen_at TEXT,eligible INTEGER)')
            c.executemany('INSERT INTO show_discovery VALUES(?,?,?)', [
                (1, (END - timedelta(days=3)).isoformat(), 1),
                (2, (END - timedelta(days=2)).isoformat(), 0),
                (3, (END - timedelta(days=8)).isoformat(), 1),
                (4, END.isoformat(), 1),
                (5, (END - timedelta(days=1)).isoformat(), 1)])
        catalog = [{'show_id': i, 'dedupe_key': str(i)} for i in range(1, 6)]
        with patch('concert_discovery.weekly_digest.get_shows', return_value=catalog), patch('concert_discovery.reconciliation.key_aliases', return_value={'old-key': '5'}):
            self.assertEqual([s['show_id'] for s in new_shows(END - timedelta(days=7), END, self.db, ['old-key'])], [1])

    def test_full_metadata_and_html_escaping(self):
        artist = {'display_name': 'Band <script>', 'genre': 'indie-rock', 'spotify_profile_url': 'https://open.spotify.com/artist/example', 'image_url': 'https://example.com/photo.jpg'}
        show = {'performance_start': '2026-11-02 20:00:00', 'title': 'Band', 'venue_id': 'sierra-nevada', 'venue_name': 'Sierra Nevada · Mills River',
                'audience_artist': artist, 'headliners': [artist], 'audience': 550000, 'listener_growth_6m': -12.4,
                'ticket_url': 'https://tickets.example.com/show', 'official_event_url': None, 'sources': [],
                'event_classification': {'category': 'cover_band'}, 'sold_out': {'status': 'sold_out'}}
        prices = {'tickets.example.com/show': {'min': 45.4, 'max': 50}}
        content, plain = render([show], 'https://example.com/unsubscribe', END, prices)
        for value in ('550k', '-12%', '$45+', 'Sold out', 'Cover Band', 'Sierra Nevada', 'Add to calendar', 'Listen on Spotify', 'Unsubscribe'):
            self.assertIn(value, content)
        self.assertIn('Band &lt;script&gt;', content)
        self.assertNotIn('<script>', content)
        self.assertIn('Spotify Listeners: 550k', plain)
        self.assertIn('#b84343', content)

    def test_missing_spotify_no_listen_link_and_zero_is_not_unknown(self):
        show = {'performance_start': '2026-11-02', 'title': 'An event', 'venue_id': 'v', 'venue_name': 'Venue', 'headliners': [],
                'audience_artist': None, 'audience': 0, 'listener_growth_6m': 0, 'ticket_url': None, 'official_event_url': None,
                'venue_calendar_url': 'https://example.com', 'sources': [], 'event_classification': {'category': 'events'}}
        content, _ = render([show], 'https://example.com/unsubscribe', END, {})
        self.assertNotIn('Listen on Spotify', content)
        self.assertIn('&lt; 1k', content)
        self.assertIn('+0%', content)

    def execute(self, store, shows=None, error=None):
        with patch('concert_discovery.weekly_digest.new_shows', return_value=shows if shows is not None else [{'dedupe_key': 'concert'}]), \
             patch('concert_discovery.weekly_digest.render', return_value=('html', 'plain')), \
             patch('concert_discovery.weekly_digest.send_email', return_value='message-id', side_effect=error) as send:
            result = run(store, 'sender@example.com', 'secret', END + timedelta(hours=1), self.db)
            return result, send.call_count

    def test_success_and_rerun_do_not_duplicate(self):
        store = FakeStore()
        result, calls = self.execute(store)
        self.assertEqual((result['sent'], calls), (1, 1))
        self.assertEqual(self.execute(store)[1], 0)
        self.assertEqual(store.finished, ['sent'])

    def test_empty_week_is_recorded_without_email(self):
        store = FakeStore()
        result, calls = self.execute(store, [])
        self.assertEqual((result['empty'], calls), (1, 0))
        self.assertEqual(store.finished, ['empty'])

    def test_optout_after_listing_is_honored(self):
        store = FakeStore(); store.active = False
        self.assertEqual(self.execute(store)[1], 0)

    def test_uncertain_acceptance_does_not_blindly_retry(self):
        store = FakeStore()
        result, calls = self.execute(store, error=smtplib.SMTPServerDisconnected('connection lost'))
        self.assertEqual((result['uncertain'], calls), (1, 1))
        self.assertEqual(store.finished, ['uncertain'])
        self.assertEqual(self.execute(store)[1], 0)

    def test_stale_catalog_blocks_send(self):
        self.db.with_name('freshness.json').write_text(json.dumps({'refreshed_at': (END - timedelta(days=3)).isoformat()}))
        with self.assertRaisesRegex(RuntimeError, 'successful refresh'):
            self.execute(FakeStore())

    def test_smtp_sends_html_and_plaintext_only_to_recipient(self):
        smtp = Mock(); smtp.send_message.return_value = {}
        with patch('concert_discovery.weekly_digest.smtplib.SMTP_SSL') as factory:
            factory.return_value.__enter__.return_value = smtp
            send_email('sender@example.com', 'app password', 'recipient@example.com', 'Subject', '<b>HTML</b>', 'Plaintext', 'https://example.com/unsubscribe')
        smtp.login.assert_called_once_with('sender@example.com', 'apppassword')
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'recipient@example.com')
        self.assertEqual(message['List-Unsubscribe'], '<https://example.com/unsubscribe>')
        self.assertEqual([part.get_content_type() for part in message.iter_parts()], ['text/plain', 'text/html'])

    def test_atomic_claim_and_scoped_unsubscribe(self):
        store = EmailStore('https://example.supabase.co', 'private-key')
        with patch.object(store, 'request', side_effect=[[], []]) as request:
            self.assertFalse(store.claim('user', END.isoformat(), ['show']))
            self.assertEqual(request.call_args.kwargs['params']['status'], 'eq.failed')
        with patch.object(store, 'request', return_value=[{'enabled': False}]) as request:
            self.assertTrue(store.unsubscribe('a' * 43))
            self.assertEqual(request.call_args.kwargs['params'], {'unsubscribe_token': 'eq.' + 'a' * 43})


if __name__ == '__main__': unittest.main()
