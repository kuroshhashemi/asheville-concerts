"""Private, server-only signed-in activity; no anonymous visitor tracking."""
from collections import Counter
from datetime import datetime, timezone
import requests
import hashlib
OWNER_EMAIL_HASH = '3429c2562e8c5392b948769a63299586e4537d11f6d8cd8a960daa16442e9e86'

class ActivityStore:
    def __init__(self, url, secret):
        self.base = url.rstrip('/').removesuffix('/rest/v1') + '/rest/v1/'
        self.headers = {'apikey': secret, 'Content-Type': 'application/json'}

    def touch(self, user_id, identity):
        if not identity.get('email') or identity.get('email_verified') is False:
            raise ValueError('Verified email required')
        response = requests.post(self.base + 'app_user_activity', headers={**self.headers, 'Prefer': 'resolution=merge-duplicates,return=minimal'},
            params={'on_conflict': 'user_id'}, json={'user_id': user_id, 'email': identity['email'],
            'display_name': identity.get('name') or '', 'last_active_at': datetime.now(timezone.utc).isoformat()}, timeout=8)
        response.raise_for_status()

    def overview(self):
        def read(table, fields):
            response = requests.get(self.base + table, headers=self.headers, params={'select': fields, 'limit': 10000}, timeout=10)
            response.raise_for_status()
            return response.json()
        users = read('app_user_activity', 'user_id,email,display_name,first_seen_at,last_active_at')
        statuses = read('user_show_statuses', 'user_id,status')
        try:
            subscriptions={r['email'].strip().casefold():bool(r['enabled']) for r in read('email_subscriptions','email,enabled')}
        except requests.RequestException:
            subscriptions=None
        counts = {}
        for status in statuses:
            counts.setdefault(status['user_id'], Counter())[status['status']] += 1
        return [{**u, 'emails':('Unknown' if subscriptions is None else ('On' if subscriptions.get(u['email'].strip().casefold(),False) else 'Off')), 'hidden': counts.get(u['user_id'], {}).get('Pass', 0),
                'interested': counts.get(u['user_id'], {}).get('Interested', 0),
                'going': counts.get(u['user_id'], {}).get('Going', 0)} for u in users]


def is_owner(identity, owner_email):
    email = identity.get('email', '').casefold()
    return bool(email and identity.get('email_verified') is not False and
                (email == owner_email.casefold() if owner_email else hashlib.sha256(email.encode()).hexdigest() == OWNER_EMAIL_HASH))


def admin_view(st, store, identity, owner_email):
    if not is_owner(identity, owner_email):
        return
    with st.expander('App activity · owner only'):
        st.caption('Signed-in activity starts with the next visit. Updated at most once every five minutes during use. Counts are current saved choices, including past shows.')
        if st.button('Refresh activity', key='refresh_activity'):
            pass
        try:
            from zoneinfo import ZoneInfo
            rows = store.overview()
            def local(value):
                return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%b %d, %Y %I:%M %p')
            st.dataframe([{'Name': r['display_name'], 'Email': r['email'], 'First recorded visit (ET)': local(r['first_seen_at']),
                           'Last active (ET)': local(r['last_active_at']), 'Emails': r['emails'], 'Hidden': r['hidden'], 'Interested': r['interested'], 'Going': r['going']} for r in rows], hide_index=True, width='stretch')
        except Exception:
            st.warning('Activity data is temporarily unavailable.')
