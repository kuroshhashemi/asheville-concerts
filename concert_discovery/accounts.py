"""Server-only Google identity and persistent personal decisions."""
import hashlib
from datetime import datetime, timezone
import requests

STATUSES={'Unread','Pass','Interested','Going'}

def user_key(identity):
    subject=identity.get('sub')
    if not subject:raise ValueError('Missing verified Google identity')
    return hashlib.sha256(('google:'+subject).encode()).hexdigest()

class StatusStore:
    def __init__(self,url,secret):
        self.url=url.rstrip('/').removesuffix('/rest/v1')+'/rest/v1/user_show_statuses'
        self.headers={'apikey':secret,'Content-Type':'application/json'}
    def load(self,user_id):
        r=requests.get(self.url,headers=self.headers,params={'user_id':'eq.'+user_id,'select':'show_key,status'},timeout=12)
        r.raise_for_status()
        return {x['show_key']:x['status'] for x in r.json()}
    def save(self,user_id,show_key,status):
        if status not in STATUSES:raise ValueError('Invalid status')
        r=requests.post(self.url,headers={**self.headers,'Prefer':'resolution=merge-duplicates,return=minimal'},
          params={'on_conflict':'user_id,show_key'},json={'user_id':user_id,'show_key':show_key,'status':status,'updated_at':datetime.now(timezone.utc).isoformat()},timeout=12)
        r.raise_for_status()

    def load_filters(self,user_id):
        url=self.url.replace('/user_show_statuses','/user_filter_settings')
        r=requests.get(url,headers=self.headers,params={'user_id':'eq.'+user_id,'select':'preferences'},timeout=12)
        r.raise_for_status()
        rows=r.json()
        return rows[0]['preferences'] if rows else None

    def save_filters(self,user_id,preferences):
        url=self.url.replace('/user_show_statuses','/user_filter_settings')
        r=requests.post(url,headers={**self.headers,'Prefer':'resolution=merge-duplicates,return=minimal'},params={'on_conflict':'user_id'},
          json={'user_id':user_id,'preferences':preferences,'updated_at':datetime.now(timezone.utc).isoformat()},timeout=12)
        r.raise_for_status()
