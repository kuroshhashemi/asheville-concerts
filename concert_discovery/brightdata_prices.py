"""Cached, bounded Bright Data ticket prices. No per-visitor API calls."""
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit
from pathlib import Path
from concert_discovery.storage import connect,DATABASE_PATH,utc_now
from concert_discovery.api_sources import secret
from concert_discovery.prices import load,for_show,from_ticket_markup,save,url_key
import sqlite3,requests

MONTHLY_LIMIT=1000 # Conservative rolling32-day cap, below shared5000 free credits.
HOSTS={'etix.com','tixr.com','wl.eventim.us','wl.seetickets.us'}

def reserve(db_path):
    with sqlite3.connect(Path(db_path).with_name('api_budget.sqlite3'),timeout=20) as c:
        c.execute('CREATE TABLE IF NOT EXISTS brightdata_attempts(at TEXT)')
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT count(*) FROM brightdata_attempts WHERE julianday(at)>=julianday('now','-32 days')").fetchone()[0]>=MONTHLY_LIMIT:return False
        c.execute('INSERT INTO brightdata_attempts VALUES(?)',(utc_now(),))
    return True

def refresh(db_path=DATABASE_PATH,limit=6,shows=None,workers=1):
    key=secret('BRIGHTDATA_API_KEY');zone=secret('BRIGHTDATA_UNLOCKER_ZONE')
    result={'brightdata_requests':0,'brightdata_prices_saved':0,'brightdata_failed':0}
    if not key or not zone:return {**result,'brightdata_state':'not_configured'}
    from concert_discovery.discovery import get_shows
    shows=get_shows(db_path) if shows is None else shows
    prices=load();seen=set();cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    with connect(db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS brightdata_price_checks(url_key TEXT PRIMARY KEY,checked_at TEXT,status TEXT)')
        recent={r[0] for r in c.execute("SELECT url_key FROM brightdata_price_checks WHERE (status='priced' AND checked_at>=?) OR checked_at>=?",(cutoff,(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()))}
    jobs=[]
    for show in sorted(shows,key=lambda s:(for_show(s,prices) is not None,not bool(s.get('just_announced')),s.get('performance_start',''))):
        if show.get('sold_out') or show.get('on_sale_label'):continue
        url=show.get('ticket_url') or '';parsed=urlsplit(url);host=(parsed.hostname or '').removeprefix('www.');identity=url_key(url)
        if parsed.scheme!='https' or host not in HOSTS or identity in seen or identity in recent:continue
        existing=for_show(show,prices)
        if existing and existing.get('observed_at',existing.get('checked_at',''))>=cutoff:continue
        seen.add(identity);jobs.append((url,identity))
        if len(jobs)>=limit:break
    if limit<=0:return result
    def fetch(job):
        url,identity=job
        try:
            response=requests.post('https://api.brightdata.com/request',headers={'Authorization':'Bearer '+key},
                json={'zone':zone,'url':url,'format':'raw'},timeout=90)
            return url,identity,response.status_code,response.text
        except requests.RequestException:return url,identity,0,''
    from concurrent.futures import ThreadPoolExecutor
    workers=max(1,min(workers,3))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for offset in range(0,len(jobs),workers):
            batch=[]
            for job in jobs[offset:offset+workers]:
                if not reserve(db_path):result['brightdata_state']='budget_reached';break
                batch.append(job);result['brightdata_requests']+=1
            if not batch:break
            stop=False
            for url,identity,http,markup in pool.map(fetch,batch):
                price=from_ticket_markup(url,markup) if http==200 else None
                if markup and http==200:
                    from concert_discovery.availability import record_ticket_page
                    record_ticket_page(url,markup,db_path)
                status='priced' if price else 'unavailable' if http==200 else 'failed'
                if price:
                    save({'source_url':url,'source_name':'Bright Data ticket provider'},price)
                    result['brightdata_prices_saved']+=1
                else:result['brightdata_failed']+=1
                with connect(db_path) as c:
                    c.execute('INSERT OR REPLACE INTO brightdata_price_checks VALUES(?,?,?)',(identity,utc_now(),status))
                    if markup and http==200:
                        from concert_discovery.source_links import schema,encode_markup
                        schema(c);c.execute('INSERT OR REPLACE INTO identity_page_cache VALUES(?,?,?,?)',(url,encode_markup(markup),http,utc_now()))
                if http in (400,401,402,403,429):stop=True;result['brightdata_state']='http_'+str(http)
            print('Price batch:',result,flush=True)
            if stop or result.get('brightdata_state')=='budget_reached':break
    return result

if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=6);args=parser.parse_args()
    print(json.dumps(refresh(limit=max(0,min(args.limit,20)))))
