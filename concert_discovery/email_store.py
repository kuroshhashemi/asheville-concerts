"""Private subscription state and atomic delivery claims, stored outside the catalog."""
import secrets
import uuid
from datetime import datetime, timezone
import requests


def now():
    return datetime.now(timezone.utc).isoformat()


class EmailStore:
    def __init__(self, url, secret):
        self.url = url.rstrip('/').removesuffix('/rest/v1') + '/rest/v1/'
        self.headers = {'apikey': secret, 'Content-Type': 'application/json'}

    def request(self, method, table, *, params=None, data=None, prefer=None):
        headers = dict(self.headers)
        if prefer:
            headers['Prefer'] = prefer
        r = requests.request(method, self.url + table, headers=headers,
                             params=params, json=data, timeout=15)
        if not r.ok:
            # Never propagate response URLs/bodies containing email addresses or tokens.
            raise RuntimeError(f'Private email storage returned HTTP {r.status_code}')
        return r.json() if r.content else []

    def get(self, email):
        rows = self.request('GET', 'email_subscriptions', params={'email': 'eq.' + email.strip().casefold(), 'select': '*'})
        return rows[0] if rows else None

    def set_enabled(self, email, enabled, user_id=None):
        email = email.strip().casefold()
        if not email or '@' not in email or '\n' in email or '\r' in email:
            raise ValueError('A verified email address is required')
        existing = self.get(email)
        if existing:
            updates = {'enabled': bool(enabled), 'updated_at': now()}
            if user_id:
                updates['user_id'] = user_id
            if enabled and not existing['enabled']:
                updates.update(subscribed_at=now(), last_processed_at=None,
                               unsubscribe_token=secrets.token_urlsafe(32))
            rows = self.request('PATCH', 'email_subscriptions',
                                params={'subscription_id': 'eq.' + existing['subscription_id']},
                                data=updates, prefer='return=representation')
            return rows[0]
        rows = self.request('POST', 'email_subscriptions', data={
            'subscription_id': str(uuid.uuid4()), 'email': email, 'user_id': user_id,
            'enabled': bool(enabled), 'unsubscribe_token': secrets.token_urlsafe(32),
            'subscribed_at': now(), 'updated_at': now()}, prefer='return=representation')
        return rows[0]

    def unsubscribe(self, token):
        if not isinstance(token, str) or not 32 <= len(token) <= 100:
            return False
        rows = self.request('PATCH', 'email_subscriptions',
                            params={'unsubscribe_token': 'eq.' + token},
                            data={'enabled': False, 'updated_at': now()}, prefer='return=representation')
        return bool(rows)

    def enabled(self):
        return self.request('GET', 'email_subscriptions', params={'enabled': 'eq.true', 'select': '*', 'order': 'subscription_id'})

    def is_enabled(self, subscription_id):
        rows = self.request('GET', 'email_subscriptions', params={
            'subscription_id': 'eq.' + subscription_id, 'enabled': 'eq.true', 'select': 'subscription_id'})
        return bool(rows)

    def sent_keys(self, subscription_id):
        rows = self.request('GET', 'email_digest_deliveries', params={
            'subscription_id': 'eq.' + subscription_id, 'status': 'eq.sent', 'select': 'show_keys'})
        return {key for row in rows for key in row['show_keys']}

    def claim(self, subscription_id, end, keys):
        params = {'on_conflict': 'subscription_id,period_end'}
        data = {'subscription_id': subscription_id, 'period_end': end, 'status': 'sending',
                'show_keys': keys, 'attempted_at': now()}
        rows = self.request('POST', 'email_digest_deliveries', params=params, data=data,
                            prefer='resolution=ignore-duplicates,return=representation')
        if rows:
            return True
        # Only a conclusively rejected message may retry. An uncertain SMTP outcome never auto-retries.
        rows = self.request('PATCH', 'email_digest_deliveries', params={
            'subscription_id': 'eq.' + subscription_id, 'period_end': 'eq.' + end, 'status': 'eq.failed'},
            data={'status': 'sending', 'show_keys': keys, 'attempted_at': now()}, prefer='return=representation')
        return bool(rows)

    def finish(self, subscription_id, end, status, message_id=None):
        self.request('PATCH', 'email_digest_deliveries', params={
            'subscription_id': 'eq.' + subscription_id, 'period_end': 'eq.' + end},
            data={'status': status, 'message_id': message_id, 'sent_at': now() if status == 'sent' else None})
        if status in ('sent', 'empty'):
            self.request('PATCH', 'email_subscriptions', params={'subscription_id': 'eq.' + subscription_id},
                         data={'last_processed_at': end, 'updated_at': now()})
