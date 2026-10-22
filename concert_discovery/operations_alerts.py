"""Private owner alerts, deduplicated and throttled; no subscriber distribution."""
import os,hashlib,smtplib,ssl
from datetime import datetime,timezone,timedelta
from email.message import EmailMessage
from concert_discovery.storage import connect,DATABASE_PATH,utc_now

def readable_report(problems,db_path,now):
 from zoneinfo import ZoneInfo
 from concert_discovery.prices import load,for_show,label
 prices=load();lines=[f'{len(problems)} data checks need attention.',
  'These checks have repeatedly failed or remained unprocessed. This warning alone does not stop the weekly email.',
  'Saved values are retained. A failed price check does not mean a show is sold out.','']
 fields={'tickets':'Ticket price / availability','spotify':'Spotify match','listeners':'Spotify listeners','photo':'Artist photo','genre':'Genre','growth':'Six-month listener growth','venue_icon':'Venue icon'}
 def stamp(value):
  if not value:return 'Not attempted yet'
  try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%a %b %d, %I:%M %p %Z')
  except ValueError:return 'Unknown'
 with connect(db_path) as c:
  tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  for item in problems:
   show=None;heading='Artist awaiting identification'
   if item['entity_type']=='show' and 'shows' in tables:
    r=c.execute('SELECT * FROM shows WHERE dedupe_key=?',(item['entity_key'],)).fetchone()
    if r:
     show=dict(r);heading=show.get('title') or 'Untitled show'
     venue=c.execute('SELECT name FROM venues WHERE venue_id=?',(show['venue_id'],)).fetchone() if 'venues' in tables else None
     day=show.get('performance_start','')[:10]
     try:day=datetime.fromisoformat(day).strftime('%b %d, %Y')
     except ValueError:pass
     heading+=' — '+(venue[0] if venue else 'Venue unknown')+' — '+day
     show['sources']=[dict(r) for r in c.execute('SELECT source_url FROM show_sources WHERE show_id=?',(show['show_id'],))] if 'show_sources' in tables else []
   elif item['entity_type']=='artist' and 'artists' in tables:
    r=c.execute('SELECT display_name FROM artists WHERE artist_id=?',(item['entity_key'],)).fetchone()
    if r:heading=r[0]
   reason='The automated page check did not return usable data; the saved result does not establish the exact cause.' if item['status']=='blocked' else 'A check was attempted, but the field remains unresolved.' if item.get('checked_at') else 'Still queued; no completed check is recorded.'
   raw=(item.get('detail') or '').lower()
   if 'price extraction failed' in raw:reason='Tickets were available, but the collector could not extract their price.'
   elif '403' in raw:reason='The source refused automated access (HTTP 403).'
   elif '429' in raw or 'rate_limit' in raw:reason='The source temporarily limited requests.'
   elif 'timeout' in raw:reason='The source did not respond before the request timed out.'
   retry=item.get('next_attempt_at')
   try:due=not retry or datetime.fromisoformat(retry.replace('Z','+00:00'))<=now
   except (ValueError,TypeError):due=True
   lines.extend([heading,'Check: '+fields.get(item['field'],item['field'].replace('_',' ').capitalize()),'Problem: '+reason])
   if show and item['field']=='tickets':
    price=for_show(show,prices)
    lines.append('Saved price: '+(label(price)+' (retained; refresh unsuccessful)' if price else 'None yet'))
    if show.get('ticket_url'):lines.append('Ticket page: '+show['ticket_url'])
   lines.extend(['Last attempt: '+stamp(item.get('checked_at')),
    'Retry: '+('Eligible now; next daily collection, subject to provider/request limits.' if due else 'Eligible after '+stamp(retry)+'; retried during collection.'),''])
 return '\n'.join(lines)


def notify(kind,detail,db_path=DATABASE_PATH,now=None):
 sender=os.environ.get('EMAIL_SENDER');password=os.environ.get('EMAIL_APP_PASSWORD')
 if not sender or not password:return {'operations_alert':'not_configured'}
 now=now or datetime.now(timezone.utc);signature=hashlib.sha256(detail.encode()).hexdigest()
 with connect(db_path) as c:
  c.execute('CREATE TABLE IF NOT EXISTS operations_alerts(kind TEXT PRIMARY KEY,signature TEXT,sent_at TEXT)')
  old=c.execute('SELECT * FROM operations_alerts WHERE kind=?',(kind,)).fetchone()
  if old and (old['signature']==signature or now-datetime.fromisoformat(old['sent_at'])<timedelta(hours=24)):return {'operations_alert':'unchanged_or_throttled'}
 msg=EmailMessage();msg['From']=sender;msg['To']=sender
 msg['Subject']='Asheville Soundcheck: '+('sign-in needs attention' if kind.startswith('login-') else 'weekly email held' if kind=='digest-held' else 'shows withheld from weekly email' if kind.startswith('digest-withheld:') else 'collection needs attention')
 msg.set_content(detail+'\n\nOwner-only diagnostic: https://asheville-soundcheck.streamlit.app/')
 try:
  with smtplib.SMTP_SSL('smtp.gmail.com',465,context=ssl.create_default_context(),timeout=20) as smtp:
   smtp.login(sender,password.replace(" ",""));smtp.send_message(msg)
 except (OSError,smtplib.SMTPException):return {'operations_alert':'send_failed'}
 with connect(db_path) as c:c.execute('INSERT OR REPLACE INTO operations_alerts VALUES(?,?,?)',(kind,signature,now.isoformat()))
 return {'operations_alert':'sent_to_owner'}


def check(db_path=DATABASE_PATH,now=None):
 from concert_discovery.metadata_outcomes import schema
 now=now or datetime.now(timezone.utc)
 with connect(db_path) as c:
  schema(c);rows=[dict(r) for r in c.execute('SELECT * FROM metadata_outcomes WHERE active=1')]
 problems=[]
 for r in rows:
  since=r['first_failure_at'] if r['status']=='blocked' else r['first_seen_at']
  age=now-datetime.fromisoformat(since) if since else timedelta(0)
  if (r['status']=='blocked' and r['consecutive_failures']>=2 and age>=timedelta(hours=24)) or (r['status'] in ('pending','queued') and age>=timedelta(hours=48)):
   problems.append(dict(r))
 if not problems:return {'operations_alert':'no_persistent_failures'}
 problems.sort(key=lambda r:(r['entity_type'],r['entity_key'],r['field']))
 detail=readable_report(problems,db_path,now)
 return notify('metadata-failures',detail,db_path,now)
