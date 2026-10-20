"""Validate listings during collection and again before email delivery."""
from datetime import datetime
from concert_discovery.storage import connect
from concert_discovery.digest_validation import conflicts
from concert_discovery.ticket_destinations import generic_destination

def partition(shows,catalog,db_path):
    reasons={}
    for s in shows:
        missing=[label for key,label in (('title','title'),('venue_id','venue'),('performance_start','date')) if not s.get(key)]
        try:datetime.fromisoformat(s.get('performance_start',''))
        except (ValueError,TypeError):
            if 'date' not in missing:missing.append('date')
        if not s.get('sources'):missing.append('source')
        if missing:reasons[s['show_id']]=['Missing or invalid '+', '.join(missing)]
    with connect(db_path) as c:
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='official_ticket_links'").fetchone()
        pages={r['show_id']:r['source_url'] for r in c.execute('SELECT * FROM official_ticket_links') if not generic_destination(r['source_url'])} if exists else {}
    valid=[s for s in catalog if s.get('venue_id') and s.get('performance_start') and s.get('title')]
    candidates=[s for s in shows if s['show_id'] not in reasons]
    for conflict in conflicts(candidates,valid,pages):
        explanation=conflict['reason']+': '+' / '.join(conflict['times'])
        for sid in conflict['show_ids']:
            if any(s['show_id']==sid for s in shows):reasons.setdefault(sid,[]).append(explanation)
    held=[{'show_id':s['show_id'],'dedupe_key':s['dedupe_key'],'title':s.get('title') or '(untitled)',
           'date':s.get('performance_start') or '(missing)','venue':s.get('venue_name') or s.get('venue_id') or '(missing)',
           'reasons':sorted(set(reasons[s['show_id']]))} for s in shows if s['show_id'] in reasons]
    return [s for s in shows if s['show_id'] not in reasons],held
