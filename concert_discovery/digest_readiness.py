"""Fail closed when newly selected digest rows still have unattempted enrichment.

Unavailable data is allowed only with collection evidence. This performs no
network requests and does not mistake a recent catalog refresh for enrichment.
"""
from concert_discovery.storage import connect,DATABASE_PATH
from concert_discovery.prices import load,for_show,url_key

def audit(shows,db_path=DATABASE_PATH):
    from datetime import datetime,timezone,timedelta
    cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    prices=load();pending=[]
    with connect(db_path) as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def exists(table,query,args):return table in tables and c.execute(query,args).fetchone() is not None
        for show in shows:
            gaps=[]
            if not show.get('sources'):gaps.append('show source')
            for a in show.get('headliners',[]):
                aid=a['artist_id'];sid=a.get('spotify_artist_id')
                identity_checked=bool(sid) or exists('artist_matching_jobs','SELECT 1 FROM artist_matching_jobs WHERE artist_id=? AND attempts>0',(aid,))
                if not identity_checked:gaps.append('Spotify matching: '+a['display_name']);continue
                # Without a confirmed identity, Spotify-only fields cannot be collected.
                if not sid:continue
                if not exists('artist_metric_snapshots','SELECT 1 FROM artist_metric_snapshots WHERE artist_id=? AND source_url=? AND retrieved_at>=?',(aid,a.get('spotify_profile_url'),cutoff)):
                    gaps.append('listeners/photo: '+a['display_name'])
                if not exists('history_checks','SELECT 1 FROM history_checks WHERE spotify_id=? AND checked_at>=?',(sid,cutoff[:10])):
                    gaps.append('growth: '+a['display_name'])
            if for_show(show,prices) is None and not show.get('on_sale_label') and not show.get('sold_out'):
                urls=[show.get('ticket_url'),show.get('official_event_url')]+[s.get('source_url') for s in show.get('sources',[])]
                attempted=False
                for url in filter(None,urls):
                    key=url_key(url)
                    for table in ('ticket_price_checks','brightdata_price_checks','rendered_price_checks','cloud_rendered_price_checks'):
                        if exists(table,'SELECT 1 FROM '+table+' WHERE url_key=?',(key,)):attempted=True
                    if exists('identity_page_cache','SELECT 1 FROM identity_page_cache WHERE url=?',(url,)):attempted=True
                if not attempted and 'ticket_price_checks' in tables:
                    from urllib.parse import urlsplit
                    provider=(urlsplit(show.get('ticket_url') or '').hostname or '').removeprefix('www.')
                    # The collector's daily provider circuit breaker deliberately
                    # reuses a failed provider check instead of repeating it per show.
                    blocked=c.execute("SELECT url FROM ticket_price_checks WHERE status IN ('blocked','error') AND checked_at>=?",((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),)).fetchall()
                    attempted=bool(provider) and any((urlsplit(r[0]).hostname or '').removeprefix('www.')==provider for r in blocked)
                # A venue page lookup is not a Ticketmaster inventory check.
                from concert_discovery.ticketmaster_prices import event_id
                tm_ids={event_id(u) for u in urls if event_id(u)}
                if tm_ids:
                    attempted=all(exists('ticketmaster_price_checks',
                        'SELECT 1 FROM ticketmaster_price_checks WHERE event_id=? AND checked_at>=?',
                        (eid,cutoff)) for eid in tm_ids)
                if not attempted:gaps.append('ticket price')
            # Durable outcomes distinguish unavailable observations from failed fetches.
            if 'metadata_outcomes' in tables:
                for a in show.get('headliners',[]):
                    outcomes={r['field']:r['status'] for r in c.execute("SELECT field,status FROM metadata_outcomes WHERE entity_type='artist' AND entity_key=? AND active=1",(a['artist_id'],))}
                    if outcomes.get('growth') in ('complete','unavailable','not_applicable'):gaps=[g for g in gaps if g!='growth: '+a['display_name']]
                    if all(outcomes.get(f) in ('complete','unavailable','not_applicable') for f in ('listeners','photo')):gaps=[g for g in gaps if g!='listeners/photo: '+a['display_name']]
                    for r in c.execute("SELECT field,status FROM metadata_outcomes WHERE entity_type='artist' AND entity_key=? AND active=1",(a['artist_id'],)):
                        if r['status'] in ('blocked','pending'):
                            gaps.append(r['field']+': '+a['display_name'])
                for r in c.execute("SELECT field,status FROM metadata_outcomes WHERE entity_type='show' AND entity_key=? AND active=1",(show.get('dedupe_key',''),)):
                    if r['status'] in ('blocked','pending','unresolved'):gaps.append(r['field'])
            # Genres come only from structured JamBase import fields. An imported
            # source with no genre is unavailable, not a pending prose lookup.
            if gaps:pending.append({'show_id':show['show_id'],'title':show['title'],'pending':sorted(set(gaps))})
    return pending

def require_ready(shows,db_path=DATABASE_PATH,allow_metadata_gaps=False):
    from concert_discovery.digest_validation import conflicts
    from concert_discovery.discovery import get_shows
    from concert_discovery.ticket_destinations import generic_destination
    with connect(db_path) as c:
        has_links=c.execute("SELECT 1 FROM sqlite_master WHERE name='official_ticket_links'").fetchone()
        verified_pages={r['show_id']:r['source_url'] for r in c.execute('SELECT * FROM official_ticket_links') if not generic_destination(r['source_url'])} if has_links else {}
    conflicts_found=conflicts(shows,get_shows(db_path),verified_pages)
    if conflicts_found:
        names=', '.join(sorted({r['title'] for r in conflicts_found}))
        raise RuntimeError('Digest held: possible duplicate/date conflicts: '+names)
    pending=audit(shows,db_path)
    core={'show source','date','venue','title'}
    structural=[r for r in pending if any(f.split(':')[0] in core for f in r['pending'])]
    if structural:
        raise RuntimeError('Digest held: '+str(len(structural))+' shows lack core show information')
    if pending and not allow_metadata_gaps:
        fields=sorted({f.split(':')[0] for row in pending for f in row['pending']})
        raise RuntimeError('Digest held: '+str(len(pending))+' shows need enrichment checks ('+', '.join(fields)+')')

