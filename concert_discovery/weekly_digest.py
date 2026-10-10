"""Monday new-show digest: no live data fetching, AI calls, or personal filters."""
import argparse
import html
import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone, date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo
from concert_discovery.storage import DATABASE_PATH, connect
from concert_discovery.discovery import get_shows, compact_audience
from concert_discovery.bill_presentation import name as display_name
from concert_discovery.genre_labels import genre_labels
from concert_discovery.prices import load as load_prices, for_show, label as price_label
from concert_discovery.calendar_links import google_calendar_link
from concert_discovery.email_store import EmailStore

APP_URL = 'https://asheville-soundcheck.streamlit.app/'
ZONE = ZoneInfo('America/New_York')
FIRST_SEND = date(2026, 10, 19)
VENUE_NAMES = {'sierra-nevada': 'Sierra Nevada', 'thomas-wolfe': "Harrah's", 'harrahs-arena': "Harrah's",
               'ayurprana': 'AyurPrana', 'oskar-blues-brevard': 'Oskar Blues', 'revival': 'Revival'}


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def monday_end(current):
    local = current.astimezone(ZONE)
    if local.date() < FIRST_SEND or local.weekday() != 0 or local.hour < 9:
        return None
    return local.replace(hour=9, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def new_shows(start, end, db_path=DATABASE_PATH, sent_keys=()):
    # Use exactly the visible catalog's duplicate/cancellation/recurrence rules.
    catalog = get_shows(db_path, user_id='email-view')
    with connect(db_path) as c:
        discovered = {r['show_id']: r for r in c.execute('SELECT * FROM show_discovery')}
    from concert_discovery.reconciliation import key_aliases
    aliases = key_aliases(db_path)
    already_sent = {aliases.get(key, key) for key in sent_keys}
    result = []
    for show in catalog:
        record = discovered.get(show['show_id'])
        if (record and record['eligible'] and start <= instant(record['first_seen_at']) < end
                and show['dedupe_key'] not in already_sent):
            result.append(show)
    return result


def safe_url(value):
    value = str(value or '')
    return value if urlsplit(value).scheme in ('http', 'https') else ''


def render(shows, unsubscribe_url, end, prices=None):
    prices = load_prices() if prices is None else prices
    esc = lambda value: html.escape(str(value), quote=True)
    cards, plain = [], ['Asheville Soundcheck', f'{len(shows)} newly discovered shows', APP_URL, '']
    for show in shows:
        name = display_name(show)
        venue = VENUE_NAMES.get(show['venue_id'], show['venue_name'])
        when = datetime.fromisoformat(show['performance_start']).strftime("%a %b %d '%y")
        artist = show.get('audience_artist') or next(iter(show['headliners']), {})
        genre = artist.get('genre') or next((a.get('genre') for a in show['headliners'] if a.get('genre')), None)
        genre = ', '.join(genre_labels(genre)) if genre else '—'
        listeners = compact_audience(show.get('audience'))
        growth = show.get('listener_growth_6m')
        growth_label = f'{growth:+.0f}%' if growth is not None else '—'
        growth_color = '#147d58' if growth is not None and growth >= 0 else '#b84343' if growth is not None else '#63717d'
        price = price_label(for_show(show, prices)) or '—'
        listen = safe_url(artist.get('spotify_profile_url') or next((a.get('spotify_profile_url') for a in show['headliners'] if a.get('spotify_profile_url')), None))
        buy = safe_url(show.get('ticket_url') or show.get('official_event_url') or show.get('venue_calendar_url'))
        category = show['event_classification']['category']
        tags = ([] if category == 'live_music' else [category.replace('_', ' ').title()]) + (['Sold out'] if show.get('sold_out') else [])
        image = safe_url(artist.get('image_url') or next((a.get('image_url') for a in show['headliners'] if a.get('image_url')), None))
        photo = f'<img src="{esc(image)}" width="40" height="40" alt="" style="border-radius:50%;vertical-align:middle;margin-right:10px;object-fit:cover">' if image else ''
        links = []
        if listen:
            links.append(f'<a href="{esc(listen)}" style="color:#102c43">Listen on Spotify</a>')
        if buy:
            links.append(f'<a href="{esc(buy)}" style="color:#102c43">Tickets{(" · " + esc(price)) if price != "—" else ""}</a>')
            calendar = google_calendar_link({**show, 'venue_name': venue}, name, buy)
            links.append(f'<a href="{esc(calendar)}" style="color:#102c43">Add to calendar</a>')
        cards.append(f'''<table role="presentation" width="100%" style="border-bottom:1px solid #e1e7eb;padding:18px 0"><tr><td>
<div style="font-size:13px;color:#63717d">{esc(when)} · {esc(venue)}</div>
<h2 style="font-size:20px;color:#102c43;margin:10px 0">{photo}{esc(name)}</h2>
<div style="font-size:13px;color:#63717d">{esc(genre)}{(' · ' + esc(' · '.join(tags))) if tags else ''}</div>
<p style="font-size:14px">Spotify Listeners <strong>{esc(listeners)}</strong> &nbsp; Trending <strong style="color:{growth_color}">{esc(growth_label)}</strong> &nbsp; Price <strong>{esc(price)}</strong></p>
<div style="font-size:14px">{' &nbsp; · &nbsp; '.join(links)}</div></td></tr></table>''')
        plain.extend([f'{when} | {name} | {venue}', f'{genre} | Spotify Listeners: {listeners} | Trending: {growth_label} | Price: {price}',
                      (' · '.join(tags)), *([f'Spotify: {listen}'] if listen else []), f'Tickets: {buy}', ''])
    plain.extend(['Review shows and mark Hidden, Interested or Going: ' + APP_URL, 'Unsubscribe: ' + unsubscribe_url])
    content = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f0f4f6;font-family:Arial,sans-serif;color:#102c43">
<table role="presentation" width="100%"><tr><td align="center"><table role="presentation" width="100%" style="max-width:640px;background:#fff"><tr><td style="padding:24px">
<h1 style="font-size:26px;margin:0">Asheville Soundcheck</h1><p style="color:#63717d">{len(shows)} newly discovered shows · {esc(end.astimezone(ZONE).strftime('%b %d'))}</p>
<p style="font-size:14px">All newly discovered shows, independent of your filters.</p>{''.join(cards)}
<p><a href="{APP_URL}" style="display:inline-block;background:#102c43;color:#fff;text-decoration:none;border-radius:12px;padding:12px 18px">Review on Soundcheck</a></p>
<p style="font-size:12px;color:#63717d">Trending is six-month listener growth. — means data is unavailable. Prices and availability can change.</p>
<p style="font-size:12px"><a href="{esc(unsubscribe_url)}" style="color:#63717d">Unsubscribe</a> · You opted into this weekly email.</p>
</td></tr></table></td></tr></table></body></html>'''
    return content, '\n'.join(plain)


def send_email(sender, password, recipient, subject, content, plain, unsubscribe_url):
    message = EmailMessage()
    message['From'] = formataddr(('Asheville Soundcheck', sender))
    message['To'] = recipient
    message['Subject'] = subject
    message['Message-ID'] = make_msgid(domain='gmail.com')
    message['List-Unsubscribe'] = '<' + unsubscribe_url + '>'
    message.set_content(plain)
    message.add_alternative(content, subtype='html')
    # Authentication/connection failures occur before any message submission.
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(sender, password.replace(' ', ''))
        smtp.send_message(message)
    return message['Message-ID']


def run(store, sender, password, current=None, db_path=DATABASE_PATH):
    current = current or datetime.now(timezone.utc)
    end = monday_end(current)
    if end is None:
        return {'sent': 0, 'reason': 'Outside Monday send window or before October 19'}
    freshness = Path(db_path).with_name('freshness.json')
    if not freshness.exists() or current - instant(json.loads(freshness.read_text())['refreshed_at']) > timedelta(hours=48):
        raise RuntimeError('Catalog needs a successful refresh before sending a digest')
    result = {'sent': 0, 'empty': 0, 'already_processed': 0, 'failed': 0, 'uncertain': 0}
    subscriptions = store.enabled()
    if len(subscriptions) > 200:
        raise RuntimeError('Digest exceeds the configured free-sending safeguard (200 recipients)')
    for subscription in subscriptions:
        sid = subscription['subscription_id']
        start = max(instant(subscription['subscribed_at']), instant(subscription['last_processed_at']) if subscription.get('last_processed_at') else end - timedelta(days=7))
        if start >= end:
            continue
        shows = new_shows(start, end, db_path, store.sent_keys(sid))
        if not store.claim(sid, end.isoformat(), [s['dedupe_key'] for s in shows]):
            result['already_processed'] += 1
            continue
        if not shows:
            store.finish(sid, end.isoformat(), 'empty'); result['empty'] += 1
            continue
        # Honor opt-out even if it happened after the initial subscriber listing.
        if not store.is_enabled(sid):
            store.finish(sid, end.isoformat(), 'empty'); result['empty'] += 1
            continue
        unsubscribe_url = APP_URL + '?' + urlencode({'unsubscribe': subscription['unsubscribe_token']})
        content, plain = render(shows, unsubscribe_url, end)
        try:
            mid = send_email(sender, password, subscription['email'], f'{len(shows)} new shows · Asheville Soundcheck', content, plain, unsubscribe_url)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError):
            store.finish(sid, end.isoformat(), 'failed'); result['failed'] += 1
        except Exception:
            # A disconnect during DATA may mean Gmail accepted the message; never blindly resend.
            store.finish(sid, end.isoformat(), 'uncertain'); result['uncertain'] += 1
        else:
            store.finish(sid, end.isoformat(), 'sent', mid); result['sent'] += 1
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('preview', 'test', 'send'), default='preview')
    parser.add_argument('--output', default='/tmp/soundcheck-digest-preview.html')
    args = parser.parse_args()
    current = datetime.now(timezone.utc)
    if args.mode in ('preview', 'test'):
        shows = new_shows(current - timedelta(days=7), current) or get_shows(user_id='email-view')[:5]
        unsubscribe_url = APP_URL
        if args.mode == 'test':
            store = EmailStore(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
            subscription = store.get(os.environ['EMAIL_SENDER'])
            if not subscription:
                raise RuntimeError('Register the sender subscription before sending a test')
            unsubscribe_url += '?' + urlencode({'unsubscribe': subscription['unsubscribe_token']})
        content, plain = render(shows, unsubscribe_url, current)
        Path(args.output).write_text(content)
        if args.mode == 'test':
            # Test mode never reads subscriber addresses or changes delivery history.
            send_email(os.environ['EMAIL_SENDER'], os.environ['EMAIL_APP_PASSWORD'], os.environ['EMAIL_SENDER'],
                       '[Test] Asheville Soundcheck weekly digest', content, plain, unsubscribe_url)
        print(json.dumps({'mode': args.mode, 'preview_shows': len(shows)}))
    else:
        store = EmailStore(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
        result = run(store, os.environ['EMAIL_SENDER'], os.environ['EMAIL_APP_PASSWORD'])
        print(json.dumps(result))
        if result.get('failed') or result.get('uncertain'):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
