"""Resume a bounded, explicit guest action after verified account sign-in."""
import math
import time
STATUSES={'Pass','Interested','Going'}
TTL_SECONDS=600

def validate(intent,valid_keys,aliases=None,now=None):
 if not isinstance(intent,dict) or intent.get('stage')!='signing-in':return None
 token=intent.get('token');created=intent.get('created_at');status=intent.get('status');key=intent.get('show_key')
 if not isinstance(token,str) or not 1<=len(token)<=100:return None
 if isinstance(created,bool) or not isinstance(created,(int,float)) or not math.isfinite(created):return None
 age=(time.time() if now is None else now)-created/1000
 if age < -30 or age > TTL_SECONDS or status not in STATUSES or not isinstance(key,str):return None
 key=(aliases or {}).get(key,key)
 if key not in valid_keys:return None
 return {'show_key':key,'status':status,'token':token}

def apply(change,store,user_id,saved):
 """Absolute status assignment makes a repeated delivery safe; no toggle replay."""
 previous=saved.get(change['show_key'],'Unread')
 if previous!=change['status']:store.save(user_id,change['show_key'],change['status'])
 saved[change['show_key']]=change['status']
 return previous
