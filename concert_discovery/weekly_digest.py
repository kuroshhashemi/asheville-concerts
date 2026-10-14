"""Monday new-show digest: no live data fetching, AI calls, or personal filters."""
import argparse
import base64
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
from concert_discovery.email_images import play_button, revival_icon, inline_images

EMAIL_ASSETS = 'https://raw.githubusercontent.com/kuroshhashemi/asheville-concerts/main/concert_discovery/assets/email-icons/'
APP_URL = 'https://asheville-soundcheck.streamlit.app/'
ZONE = ZoneInfo('America/New_York')
FIRST_SEND = date(2026, 10, 19)
SUBJECT = 'Asheville Soundcheck - New Announced Shows'
VENUE_NAMES = {'sierra-nevada': 'Sierra Nevada', 'thomas-wolfe': "Harrah's", 'harrahs-arena': "Harrah's",
               'ayurprana': 'AyurPrana', 'oskar-blues-brevard': 'Oskar Blues', 'revival': 'Revival', 'pulp':'The Orange Peel'}


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
                and show['dedupe_key'] not in already_sent
                and show.get('audience') is not None
                and show.get('event_classification',{}).get('category')=='live_music'):
            result.append(show)
    return result


def safe_url(value):
    value = str(value or '')
    return value if urlsplit(value).scheme in ('http', 'https') else ''


def spotify_email_link(profile):
    """Spotify's universal link: app when supported, same artist on web otherwise.

    Email cannot run our app-detection JavaScript. Mail clients can still prevent
    app handoff; retain the original artist URL as the explicit fallback.
    """
    import re
    parsed = urlsplit(safe_url(profile))
    if parsed.hostname != 'open.spotify.com' or not re.fullmatch(r'/artist/[A-Za-z0-9]{22}', parsed.path):
        return safe_url(profile)
    web = 'https://open.spotify.com' + parsed.path
    return 'https://spotify.link/content_linking?' + urlencode({
        '$canonical_url': web, '$fallback_url': web,
        '$desktop_url': web, '$ios_url': web, '$android_url': web,
    })


def render(shows, unsubscribe_url, end, prices=None, start=None):
    prices = load_prices() if prices is None else prices
    start = start or end - timedelta(days=7)
    since = start.astimezone(ZONE).strftime('%b %d, %Y').replace(' 0',' ')
    esc = lambda value: html.escape(str(value), quote=True)
    icon = lambda name, alt: f'<img src="{EMAIL_ASSETS}{name}.png" width="20" height="20" alt="{esc(alt)}" style="vertical-align:middle;border:0">'
    max_listeners = max([show.get('audience') or 0 for show in shows] + [1])
    rows, plain = [], ['Asheville Soundcheck', f'{len(shows)} newly discovered shows since {since}', APP_URL, '']
    for show in shows:
        name = display_name(show)
        venue = VENUE_NAMES.get(show['venue_id'], show['venue_name'])
        when = datetime.fromisoformat(show['performance_start']).strftime("%a %b %d" + (" '%y" if datetime.fromisoformat(show['performance_start']).year != end.year else ""))
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
        photo = f'<img src="{esc(image)}" width="28" height="28" alt="" style="border-radius:50%;vertical-align:middle;margin-right:10px;object-fit:cover">' if image else ''
        links = []
        if listen:
            links.append(f'<a href="{esc(listen)}" style="color:#102c43">Listen on Spotify</a>')
        if buy:
            links.append(f'<a href="{esc(buy)}" style="color:#102c43">Tickets{(" · " + esc(price)) if price != "—" else ""}</a>')
            calendar = google_calendar_link({**show, 'venue_name': venue}, name, buy)
            links.append(f'<a href="{esc(calendar)}" style="color:#102c43">Add to calendar</a>')
        play = f'<a href="{esc(spotify_email_link(listen))}" title="Listen on Spotify" aria-label="Listen on Spotify"><img src="{EMAIL_ASSETS}play.png" width="29" height="29" alt="Play on Spotify" style="display:block;border:0"></a>' if listen else ''
        ticket = f'<a href="{esc(buy)}" style="display:inline-block;background:#eef2f4;color:#102c43;border-radius:8px;padding:7px;text-decoration:none">{esc(price) if price != "—" else "Tickets"}</a>' if buy else ''
        calendar_link = f'<a href="{esc(calendar)}" title="Add to calendar" style="color:#102c43;margin-left:6px">▦</a>' if buy else ''
        badges = ''.join(f'<span style="font-size:10px;background:#eef7f5;padding:3px 5px;border-radius:6px;margin-left:5px">{esc(t)}</span>' for t in ['New'] + tags)
        if price == '—' and buy:
            ticket = ticket.replace('Tickets</a>', icon('ticket', 'Buy tickets') + '</a>')
        if buy:
            calendar_link = f'<a href="{esc(calendar)}" title="Add to calendar" style="display:inline-block;background:#edf0f3;border-radius:10px;padding:6px 7px;margin-left:7px">{icon("calendar-plus", "Add to calendar")}</a>'
        artist_parts = []
        if category in ('live_music', 'cover_band'):
            for headliner in show['headliners']:
                profile = safe_url(headliner.get('spotify_profile_url'))
                head_image = safe_url(headliner.get('image_url'))
                part = (f'<img src="{esc(head_image)}" width="28" height="28" alt="" style="border-radius:50%;vertical-align:middle;margin-right:7px;object-fit:cover">' if head_image else '') + esc(headliner.get('display_name', ''))
                artist_parts.append(f'<a href="{esc(profile)}" style="color:#247e79;text-decoration:none">{part}</a>' if profile else part)
        artist_content = ' &amp; '.join(artist_parts) if artist_parts else (f'<a href="{esc(listen)}" style="color:#247e79;text-decoration:none">{photo}{esc(name)}</a>' if listen else photo + esc(name))
        venue_icon = EMAIL_ASSETS+'revival.png' if show['venue_id'] == 'revival' else safe_url(show.get('venue_icon'))
        venue_content = (f'<img src="{esc(venue_icon)}" width="18" height="18" alt="" style="vertical-align:middle;margin-right:9px">' if venue_icon else '') + esc(venue)
        bar_width = round(max(0, show.get('audience') or 0) / max_listeners * 150)
        bar_cells = (f'<td width="{bar_width}" bgcolor="#bde6de" style="width:{bar_width}px;height:6px;font-size:0;line-height:0">&nbsp;</td>' if bar_width else '')
        if bar_width < 150:
            bar_cells += f'<td width="{150-bar_width}" bgcolor="#f4f6f8" style="width:{150-bar_width}px;height:6px;font-size:0;line-height:0">&nbsp;</td>'
        audience_content = f'<div style="font-variant-numeric:tabular-nums">{esc(listeners)}</div><table role="presentation" width="150" cellspacing="0" cellpadding="0" style="width:150px;table-layout:fixed;border-collapse:collapse"><tr>{bar_cells}</tr></table>' 
        cells = [esc(when), play, artist_content + badges, venue_content, esc(genre), audience_content,
                 f'<span style="color:{growth_color}">{esc(growth_label)}</span>',
                 ticket + calendar_link]
        rows.append('<tr>' + ''.join(f'<td style="padding:11px 12px;border-bottom:1px solid #edf0f3;font-size:14px;vertical-align:middle;{("text-align:center;" if i in (1,6) else "")}{("white-space:nowrap;" if i in (0,1,3,6,7,8) else "")}">{cell}</td>' for i, cell in enumerate(cells)) + '</tr>')
        plain.extend([f'{when} | {name} | {venue}', f'{genre} | Spotify Listeners: {listeners} | Trending: {growth_label} | Price: {price}',
                      (' · '.join(tags)), *([f'Spotify: {listen}'] if listen else []), f'Tickets: {buy}', ''])
    plain.extend(['Review shows and mark Hidden, Interested or Going: ' + APP_URL, 'Unsubscribe: ' + unsubscribe_url])
    content = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#fff;font-family:Arial,sans-serif;color:#102c43">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="left"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fff"><tr><td style="padding:0">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td><h1 style="font-size:26px;margin:0">Asheville Soundcheck</h1></td><td align="right"><a href="{APP_URL}" style="display:inline-block;background:#102c43;color:#fff;text-decoration:none;border-radius:12px;padding:12px 18px;white-space:nowrap">Open app</a></td></tr></table><p style="color:#63717d">{len(shows)} newly discovered shows since {esc(since)}</p>
<table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;text-align:left;min-width:950px"><thead><tr>{''.join(f'<th style="padding:13px 12px;background:#eef7f5;color:#526071;font-size:12px;text-align:{"center" if i == 1 else "left"};white-space:nowrap">{label}</th>' for i, label in enumerate(['Date', icon('spotify','Spotify'), 'Artist', 'Venue', 'Genre', 'Spotify Listeners', 'Trending', 'Tickets']))}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<p style="font-size:14px;text-align:center"><a href="{esc(unsubscribe_url)}" style="color:#63717d">Unsubscribe</a></p>
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
        from concert_discovery.digest_readiness import require_ready
        require_ready(shows,db_path)
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
        content, plain = render(shows, unsubscribe_url, end, start=start)
        try:
            mid = send_email(sender, password, subscription['email'], SUBJECT, content, plain, unsubscribe_url)
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
    parser.add_argument('--db', type=Path, default=DATABASE_PATH)
    args = parser.parse_args()
    current = datetime.now(timezone.utc)
    if args.mode in ('preview', 'test'):
        shows = new_shows(current - timedelta(days=7), current, args.db) or get_shows(args.db, user_id='email-view')[:5]
        unsubscribe_url = APP_URL
        if args.mode == 'test':
            from concert_discovery.digest_readiness import require_ready
            require_ready(shows,args.db)
            store = EmailStore(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
            subscription = store.get(os.environ['EMAIL_SENDER'])
            if not subscription:
                raise RuntimeError('Register the sender subscription before sending a test')
            unsubscribe_url += '?' + urlencode({'unsubscribe': subscription['unsubscribe_token']})
        content, plain = render(shows, unsubscribe_url, current)
        preview = content
        for name, data in json.loads((Path(__file__).parent / 'assets/email-icons.json').read_text()).items():
            preview = preview.replace(f'cid:soundcheck-{name}', 'data:image/png;base64,' + data)
        Path(args.output).write_text(preview)
        if args.mode == 'test':
            # Test mode never reads subscriber addresses or changes delivery history.
            send_email(os.environ['EMAIL_SENDER'], os.environ['EMAIL_APP_PASSWORD'], os.environ['EMAIL_SENDER'],
                       '[Test] ' + SUBJECT, content, plain, unsubscribe_url)
        print(json.dumps({'mode': args.mode, 'preview_shows': len(shows)}))
    else:
        store = EmailStore(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
        result = run(store, os.environ['EMAIL_SENDER'], os.environ['EMAIL_APP_PASSWORD'], db_path=args.db)
        print(json.dumps(result))
        if result.get('failed') or result.get('uncertain'):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
