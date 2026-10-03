"""Bounded provider clients. API credentials never enter logs or saved responses."""
import os,json,sqlite3,re
from pathlib import Path
from datetime import date,timedelta,datetime,timezone
from urllib.parse import urlparse
import requests
from concert_discovery.event_sources import venue_id_for
from concert_discovery.storage import DATABASE_PATH

def secret(name):
    value=os.environ.get(name)
    if value:return value
    try:
        import streamlit as st
        value=st.secrets.get(name)
        if value:return value
    except Exception:pass
    # Development-only files outside the deployable project.
    path=Path(__file__).resolve().parents[2]/'work'/'research'/(name.split('_')[0].lower()+'.env')
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith(name+'='):return line.split('=',1)[1].strip().strip('\"\'')
    return None

def reserve_jambase(db_path=None):
    path=Path(db_path or DATABASE_PATH).with_name('api_budget.sqlite3')
    with sqlite3.connect(path,timeout=20) as c:
        c.execute('CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,at TEXT)')
        c.execute('BEGIN IMMEDIATE')
        # Rolling 32 days avoids guessing the billing reset date. All jobs share this file.
        count=c.execute("SELECT COUNT(*) FROM attempts WHERE at>=datetime('now','-32 days')").fetchone()[0]
        limit=min(int(os.environ.get('JAMBASE_CALL_LIMIT','900')),900)
        if count>=limit:raise RuntimeError('JamBase request budget reached; cached data retained.')
        c.execute("INSERT INTO attempts(at) VALUES(datetime('now'))")
        c.commit()

def get_json(url,params,provider):
    try:
        r=requests.get(url,params=params,timeout=25,allow_redirects=False,
                       headers={'User-Agent':'WorthAListen/1.0','Authorization':'Bearer '+secret('JAMBASE_API_KEY')} if provider=='JamBase' else {})
    except requests.RequestException:raise RuntimeError(provider+' network request failed.') from None
    if r.status_code!=200:raise RuntimeError(provider+' returned HTTP '+str(r.status_code))
    try:return r.json()
    except ValueError:raise RuntimeError(provider+' returned unreadable data.') from None

def spotify_ids(artists):
    out={}
    for a in artists:
        for link in a.get('externalLinks',{}).get('spotify',[]):
            m=re.search(r'open.spotify.com/artist/([A-Za-z0-9]{22})',link.get('url',''))
            if m:out[a['name'].casefold()]=m[1]
    return out

def event(source,identity,title,start,venue,performers,ticket=None,links=None):
    return dict(source_name=source,source_key=source+':'+identity,source_event_id=identity,
        source_url=ticket or identity,title=title,performance_start=start,venue_id=venue,
        venue_as_reported=venue,timezone='America/New_York',date_status='aggregator',date_note='Reported by '+source,
        ticket_url=ticket,artist_spotify_links=links or {},performers=performers)

def resolve_venue(name,title,start,official):
    if 'harrah' in name.lower() and 'asheville' in name.lower():
        # Match the official bill to its room, never assume arena.
        norm=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        match=[e for e in official if e['venue_id'] in ('harrahs-arena','thomas-wolfe')
               and e['performance_start'][:10]==start[:10] and
               (norm(title) in norm(e['title']) or norm(e['title']) in norm(title))]
        if match:return match[0]['venue_id']
        # Thundercat's auditorium assignment verified in source audit.
        if 'thundercat' in title.lower():return 'thomas-wolfe'
        return None
    return venue_id_for(name)

def fetch_ticketmaster(days=90,official=()):
    key=secret('TICKETMASTER_API_KEY')
    if not key:return []
    rows=[]
    for page in range(5):
        data=get_json('https://app.ticketmaster.com/discovery/v2/events.json',dict(apikey=key,latlong='35.5951,-82.5515',radius=30,unit='miles',size=200,page=page,
            startDateTime=date.today().isoformat()+'T04:00:00Z',endDateTime=(date.today()+timedelta(days=days+1)).isoformat()+'T04:59:59Z'),'Ticketmaster')
        for e in data.get('_embedded',{}).get('events',[]):
            if e.get('dates',{}).get('status',{}).get('code') in ('cancelled','canceled'):continue
            start=e['dates']['start'];day=start.get('localDate')
            if not day:continue
            venue=e.get('_embedded',{}).get('venues',[{}])[0].get('name','')
            vid=resolve_venue(venue,e['name'],day,official)
            if not vid:continue
            acts=e.get('_embedded',{}).get('attractions',[])
            performers=[dict(name=a['name'],role='headliner_candidate' if i==0 else 'support',confidence=1,note='Ticketmaster lineup order.') for i,a in enumerate(acts)]
            row=event('Ticketmaster',e['id'],e['name'],day+(' '+start['localTime'] if start.get('localTime') else ''),vid,performers,e.get('url'),spotify_ids(acts))
            row['artist_metadata']={a['name']:{'genre':(a.get('classifications') or [{}])[0].get('genre',{}).get('name')} for a in acts}
            rows.append(row)
        if page+1>=data.get('page',{}).get('totalPages',1):break
    return rows

def fetch_jambase(days=90,db_path=None):
    if not secret('JAMBASE_API_KEY'):return []
    rows=[]
    for page in range(1,7):
        reserve_jambase(db_path)
        data=get_json('https://api.data.jambase.com/v3/events',dict(geoMetroId='jambase:40',perPage=100,page=page,eventDateTo=(date.today()+timedelta(days=days)).isoformat()),'JamBase')
        for e in data.get('events',[]):
            if e.get('eventStatus') in ('cancelled','canceled'):continue
            location=e.get('location',{});name=location.get('name','')
            if location.get('address',{}).get('addressLocality') not in ('Asheville','Mills River'):continue
            vid=venue_id_for(name)
            if not vid:continue
            acts=e.get('performer',[])
            performers=[dict(name=a['name'],role='headliner' if a.get('x-isHeadliner') else 'support',confidence=1,note='JamBase explicit billing.') for a in acts]
            primary=next((o.get('url') for o in e.get('offers',[]) if o.get('category')=='ticketingLinkPrimary'),e.get('url'))
            row=event('JamBase',e['identifier'],e['name'],e['startDate'].replace('T',' '),vid,performers,primary)
            row['source_url']=e['url']
            row['artist_metadata']={a['name']:{'genre':', '.join(a.get('genre',[])),'image_url':a.get('image')} for a in acts}
            rows.append(row)
        if not data.get('pagination',{}).get('nextPage'):break
    return rows
