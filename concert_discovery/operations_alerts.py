"""Private owner alerts, deduplicated and throttled; no subscriber distribution."""
import os,json,hashlib,smtplib,ssl
from datetime import datetime,timezone,timedelta
from email.message import EmailMessage
from concert_discovery.storage import connect,DATABASE_PATH,utc_now


def notify(kind,detail,db_path=DATABASE_PATH,now=None):
 sender=os.environ.get('EMAIL_SENDER');password=os.environ.get('EMAIL_APP_PASSWORD')
 if not sender or not password:return {'operations_alert':'not_configured'}
 now=now or datetime.now(timezone.utc);signature=hashlib.sha256(detail.encode()).hexdigest()
 with connect(db_path) as c:
  c.execute('CREATE TABLE IF NOT EXISTS operations_alerts(kind TEXT PRIMARY KEY,signature TEXT,sent_at TEXT)')
  old=c.execute('SELECT * FROM operations_alerts WHERE kind=?',(kind,)).fetchone()
  if old and (old['signature']==signature or now-datetime.fromisoformat(old['sent_at'])<timedelta(hours=24)):return {'operations_alert':'unchanged_or_throttled'}
 msg=EmailMessage();msg['From']=sender;msg['To']=sender
 msg['Subject']='Asheville Soundcheck: '+('weekly email held' if kind=='digest-held' else 'collection needs attention')
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
  if (r['status']=='blocked' and r['consecutive_failures']>=2 and age>=timedelta(hours=24)) or (r['status']=='pending' and age>=timedelta(hours=48)):
   problems.append({k:r[k] for k in ('entity_type','entity_key','field','status','detail')})
 if not problems:return {'operations_alert':'no_persistent_failures'}
 problems.sort(key=lambda r:(r['entity_type'],r['entity_key'],r['field']))
 from collections import Counter
 counts=Counter(r['field']+' / '+r['status'] for r in problems)
 detail=f'{len(problems)} persistent metadata collection problems.\n'+json.dumps(dict(counts),indent=2)+'\n\nExamples (up to 10):\n'+json.dumps(problems[:10],indent=2)
 return notify('metadata-failures',detail,db_path,now)
