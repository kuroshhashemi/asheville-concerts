"""Reconcile duplicate catalog records without discarding source evidence."""
import re
from concert_discovery.storage import connect,DATABASE_PATH
def cleanup_duplicates(db_path=DATABASE_PATH):
 with connect(db_path) as c:
  rows=[dict(r) for r in c.execute('select * from shows order by show_id')];removed=set();log=[]
  def names(s):return {r[0] for r in c.execute("select artist_id from show_artists where show_id=? and billing_role like '%headliner%'",(s['show_id'],))}
  def official(s):return bool(c.execute("select 1 from show_sources where show_id=? and source_name like '%Official'",(s['show_id'],)).fetchone())
  def norm(s):return re.sub('[^a-z0-9]','',s.lower())
  for a in rows:
   if a['show_id'] in removed:continue
   for b in rows:
    if b['show_id']<=a['show_id'] or b['show_id'] in removed:continue
    if a['venue_id']!=b['venue_id'] or a['performance_start'][:10]!=b['performance_start'][:10]:continue
    if ('patio' in a['title'].lower()) != ('patio' in b['title'].lower()):continue
    na,nb=names(a),names(b);ta,tb=a['performance_start'][11:16],b['performance_start'][11:16]
    same_ticket=bool(a['ticket_url'] and b['ticket_url'] and a['ticket_url'].split('?')[0]==b['ticket_url'].split('?')[0])
    oa,ob=official(a),official(b)
    same_bill=bool(na & nb) or norm(a['title'])==norm(b['title'])
    if not same_ticket and not (same_bill and (not ta or not tb or ta==tb or oa!=ob)):continue
    if oa and ob and ta and tb and ta!=tb:continue
    keep,drop=(b,a) if ob and not oa and not same_ticket else (a,b)
    if same_ticket and ob and not oa:
     c.execute('UPDATE shows SET title=?,performance_start=?,date_status=?,date_note=?,official_event_url=? WHERE show_id=?',(b['title'],b['performance_start'],b['date_status'],b['date_note'],b['official_event_url'],a['show_id']))
    k,d=keep['show_id'],drop['show_id']
    c.execute('update show_sources set show_id=? where show_id=?',(k,d))
    # Keep the official lineup, supplement only when no official source is present.
    if not official(keep):
     c.execute('insert or ignore into show_artists select ?,artist_id,billing_role,role_confidence,role_source,role_note from show_artists where show_id=?',(k,d))
    c.execute('insert or ignore into user_show_decisions select user_id,?,decision,updated_at from user_show_decisions where show_id=?',(k,d))
    c.execute('delete from user_show_decisions where show_id=?',(d,));c.execute('delete from show_artists where show_id=?',(d,));c.execute('delete from shows where show_id=?',(d,))
    removed.add(d);log.append({'keep':k,'removed':d,'title':keep['title'],'date':keep['performance_start'][:10]})
    if d==a['show_id']:break
  return log
