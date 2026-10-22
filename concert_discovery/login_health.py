"""Private Google sign-in outcomes; never store auth tokens or raw provider errors."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
import requests


def attempt_key(value):
    try:return str(UUID(str(value)))
    except (ValueError,TypeError,AttributeError):return None

class LoginStore:
    def __init__(self,url,secret):
        self.base=url.rstrip('/').removesuffix('/rest/v1')+'/rest/v1/'
        self.headers={'apikey':secret,'Content-Type':'application/json'}
    def call(self,method,table,**kwargs):
        r=requests.request(method,self.base+table,headers={**self.headers,**kwargs.pop('headers',{})},timeout=5,**kwargs)
        r.raise_for_status()
        return r.json() if r.content else []
    def start(self,attempt_id,is_test=False):
        key=attempt_key(attempt_id)
        if not key:raise ValueError('Invalid attempt identifier')
        return self.call('POST','app_login_attempts',params={'on_conflict':'attempt_id'},headers={'Prefer':'resolution=ignore-duplicates,return=minimal'},json={'attempt_id':key,'is_test':bool(is_test)})
    def finish(self,attempt_id,identity=None,error=False,is_test=False,first_sign_in=None):
        key=attempt_key(attempt_id)
        if not key:raise ValueError('Invalid attempt identifier')
        row={'finished_at':datetime.now(timezone.utc).isoformat(),'outcome':'error' if error else 'success'}
        if error:row['error_code']='app_login_error'
        else:
            from concert_discovery.accounts import user_key
            if not identity or not identity.get('email') or identity.get('email_verified') is False:raise ValueError('Verified Google identity required')
            uid=user_key(identity)
            prior=self.call('GET','app_user_activity',params={'user_id':'eq.'+uid,'select':'user_id','limit':1}) if first_sign_in is None else []
            row.update(user_id=uid,email=identity['email'],first_sign_in=(not bool(prior) if first_sign_in is None else bool(first_sign_in)))
        self.start(key,is_test)
        # Idempotent: later visits cannot overwrite completed outcomes or registration.
        return self.call('PATCH','app_login_attempts',params={'attempt_id':'eq.'+key,'outcome':'eq.started'},headers={'Prefer':'return=minimal'},json=row)
    def recent(self,hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        return self.call('GET','app_login_attempts',params={'started_at':'gte.'+cutoff,'select':'*','order':'started_at.desc','limit':1000})
    def last_alert(self,kind):
        rows=self.call('GET','app_auth_alerts',params={'kind':'eq.'+kind,'select':'sent_at','limit':1})
        return rows[0]['sent_at'] if rows else None
    def mark_alert(self,kind):
        self.call('POST','app_auth_alerts',params={'on_conflict':'kind'},headers={'Prefer':'resolution=merge-duplicates,return=minimal'},json={'kind':kind,'sent_at':datetime.now(timezone.utc).isoformat()})


def concerns(rows,now=None):
    now=now or datetime.now(timezone.utc)
    active=[r for r in rows if not r.get('is_test')]
    errors=[r for r in active if r['outcome']=='error']
    # A started attempt may simply have been cancelled. Alert only on a cluster.
    incomplete=[]
    for r in active:
        age=now-datetime.fromisoformat(r['started_at'].replace('Z','+00:00'))
        if r['outcome']=='started' and timedelta(minutes=30)<=age<=timedelta(hours=2):incomplete.append(r)
    result=[]
    if errors:result.append(('login-errors',f'Latest recorded error: {max(r["started_at"] for r in errors)}. {len(errors)} sign-in attempt(s) reported an application authentication error in the last 24 hours. Check Login health in the owner view. No credentials or raw authentication responses were logged.'))
    if len(incomplete)>=5:result.append(('login-incomplete',f'Latest incomplete attempt: {max(r["started_at"] for r in incomplete)}. {len(incomplete)} sign-in attempts started 30 minutes to 2 hours ago without a successful return. This could indicate a login problem, but cancellations or closed tabs can produce the same signal. Check the sign-in flow.'))
    return result


def admin_view(st,store,identity,owner_email):
    from concert_discovery.activity import is_owner
    if not is_owner(identity,owner_email):return
    with st.expander('Login health · owner only'):
        st.caption('Started attempts without a return are not proven failures. First sign-in means no previous signed-in activity was saved. No passwords, tokens or raw provider errors are stored.')
        try:
            from zoneinfo import ZoneInfo
            rows=store.recent(hours=24*7)
            def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%b %d, %I:%M %p') if value else '—'
            st.dataframe([{'Started (ET)':stamp(r['started_at']),'Result':('No return observed' if r['outcome']=='started' else 'First sign-in' if r.get('first_sign_in') else r['outcome'].title()),'Completed (ET)':stamp(r.get('finished_at')),'User':r.get('email') or 'Not identified','Test':bool(r.get('is_test'))} for r in rows],hide_index=True,width='stretch')
        except requests.RequestException:st.warning('Login tracking is unavailable. The independent monitor will report storage failures.')
