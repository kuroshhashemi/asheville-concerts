"""Independent owner-only auth monitor; no sign-in or provider tokens used."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from concert_discovery.login_health import LoginStore,concerns

def monitor(store,notify,now=None):
    now=now or datetime.now(timezone.utc)
    try:
        store.check_user_storage()
        rows=store.recent(hours=48)
    except Exception:
        return {'login_monitor':notify('login-storage-unavailable','Saved choices, filters, user activity or login tracking could not be read. Supabase may be unavailable or a table permission may be broken. Check the app and Supabase; this does not establish whether Google sign-in itself works.')} 
    result={}
    for kind,message in concerns(rows,now):
        try:last=store.last_alert(kind)
        except Exception:return {'login_monitor':notify('login-storage-unavailable','Login alert history could not be read. Check Supabase monitoring permissions.')}
        if last and now-datetime.fromisoformat(last.replace('Z','+00:00'))<timedelta(hours=24):continue
        sent=notify(kind,message)
        if sent.get('operations_alert')=='sent_to_owner':store.mark_alert(kind)
        result[kind]=sent
    return result or {'login_monitor':'No actionable login issues'}

if __name__=='__main__':
    import os,json
    from concert_discovery.operations_alerts import notify
    store=LoginStore(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SECRET_KEY'])
    path=Path(os.environ.get('AUTH_MONITOR_LEDGER','/tmp/soundcheck-auth-monitor.sqlite3'))
    result=monitor(store,lambda kind,msg:notify(kind,msg,path))
    print(json.dumps(result))
    if any(isinstance(v,dict) and v.get('operations_alert') in ('send_failed','not_configured') for v in result.values()):raise RuntimeError('Login-health alert could not be delivered to owner')
