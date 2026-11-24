"""Publish only public, presentation-ready catalog data; no account state/secrets."""
import argparse,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
from concert_discovery.discovery import get_shows,compact_audience
from concert_discovery.storage import DATABASE_PATH,connect
from concert_discovery.genre_labels import genre_labels
from concert_discovery.bill_presentation import name as bill_name
from concert_discovery.calendar_links import google_calendar_link
from concert_discovery.event_classification import TYPES
from concert_discovery.prices import load,for_show,label

CORE={'brevard-music-center','asheville-music-hall','one-stop','eulogy','hellbender','grey-eagle','orange-peel','thomas-wolfe','harrahs-arena','sierra-nevada'}
LABELS={'sierra-nevada':'Sierra Nevada','thomas-wolfe':"Harrah's",'harrahs-arena':"Harrah's",'ayurprana':'AyurPrana','oskar-blues-brevard':'Oskar Blues','pulp':'The Orange Peel'}

def export(db_path=DATABASE_PATH):
    shows=get_shows(db_path,user_id='web-public');prices=load();rows=[];year=datetime.now().year
    for s in shows:
        s['venue_name']=LABELS.get(s['venue_id'],s['venue_name'])
        a=s['audience_artist'];acts=s['headliners'];name=bill_name(s)
        genre=(a.get('genre') if a else None) or next((h.get('genre') for h in acts if h.get('genre')),None)
        listen=(a.get('spotify_profile_url') if a else None) or next((h.get('spotify_profile_url') for h in acts if h.get('spotify_profile_url')),None)
        buy=s['ticket_url'] or s['official_event_url'] or s['venue_calendar_url'];price=for_show(s,prices);start=datetime.fromisoformat(s['performance_start'])
        gs=sorted({g for h in acts for g in genre_labels(h.get('genre'))} or {'Unknown'})
        rows.append(dict(id=s['dedupe_key'],show_key=s['dedupe_key'],show_id=s['show_id'],date_sort=s['performance_start'],date=start.strftime('%a %b %d')+(start.strftime(" '%y") if start.year!=year else ''),name=name,
            artist_image=(a.get('image_url') if a else None),artists=[dict(name=h['display_name'],image=h.get('image_url'),url=h.get('spotify_profile_url')) for h in acts] if s['event_classification']['category'] in ('live_music','cover_band') else [],
            venue=s['venue_name'],venue_id=s['venue_id'],venue_icon=s.get('venue_icon'),genre_options=gs,search_text=' '.join([s['title']]+[h['display_name'] for h in acts]),
            genre=', '.join(genre_labels(genre)) if genre else '—',listeners=s['audience'],listeners_label=compact_audience(s['audience']),show_type=s['event_classification']['category'].replace('_',' ').title(),type_evidence=s['event_classification'].get('evidence',''),
            growth=s['listener_growth_6m'],growth_artist=(s.get('growth_artist') or {}).get('display_name'),growth_detail=(s.get('growth_artist') or {}).get('growth_detail'),
            just_announced=s.get('just_announced'),sold_out=s.get('sold_out'),on_sale_label=s.get('on_sale_label'),status='Unread',listen=listen,buy=buy,
            calendar=google_calendar_link(s,name,buy),calendar_label='Add to Google Calendar',listener_artist=(a or {}).get('display_name'),
            price=price['min'] if price else None,price_label=label(price),resale_only=bool(price and price.get('resale_only')),price_detail=('Includes provider-stated fees.' if price and price.get('includes_fees') else 'Fee inclusion not confirmed.'),
            sources=[dict(label=x['source_name'],url=x['source_url']) for x in s['sources']]))
    max_listeners=max(1000,math.ceil(max((r['listeners'] or 0 for r in rows),default=0)/100000)*100)
    growth=[r['growth'] for r in rows if r['growth'] is not None]
    freshness=Path(db_path).with_name('freshness.json')
    saved=json.loads(freshness.read_text()) if freshness.exists() else {}
    with connect(db_path) as c:
        checks={}
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='collection_health'").fetchone():
            for r in c.execute('SELECT venue_id,status,observed_at,detail,source_url FROM collection_health ORDER BY observed_at DESC'):
                checks.setdefault(r['venue_id'],dict(r))
        aliases={}
        from concert_discovery.reconciliation import key_aliases
    aliases=key_aliases(db_path)
    payload=dict(schema=1,updated_at=max(filter(None,[saved.get('refreshed_at'),saved.get('web_updated_at')]),default=None),rows=rows,aliases=aliases,
        venues=sorted({r['venue'] for r in rows}),genres=sorted({g for r in rows for g in r['genre_options']}),types=TYPES,
        core_venues=sorted({r['venue'] for r in rows if r['venue_id'] in CORE}),
        limits=dict(listeners=max_listeners,growth=[min(-100,math.floor(min(growth,default=-100)/10)*10),max(100,math.ceil(max(growth,default=100)/10)*10)]),
        health=list(checks.values()))
    payload['version']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]
    return payload

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=DATABASE_PATH);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=export(a.db)
    if not value['updated_at'] or not value['rows']:raise SystemExit('Refusing to publish an undated or empty catalog')
    a.output.parent.mkdir(parents=True,exist_ok=True);tmp=a.output.with_suffix('.tmp');tmp.write_text(json.dumps(value,separators=(',',':')));tmp.replace(a.output)
    print(json.dumps({'rows':len(value['rows']),'updated_at':value['updated_at'],'version':value['version']}))
