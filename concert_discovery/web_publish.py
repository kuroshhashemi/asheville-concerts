"""Publish a public-only catalog into private shared storage; advance pointer last."""
import json,os,argparse
from pathlib import Path
import requests
BUCKET='soundcheck-web-catalog'
def publish(path):
    data=Path(path).read_bytes();value=json.loads(data)
    if value.get('schema')!=1 or not value.get('updated_at') or not value.get('rows'):raise ValueError('Refusing invalid catalog')
    base=os.environ['SUPABASE_URL'].rstrip('/').removesuffix('/rest/v1')+'/storage/v1'
    secret=os.environ['SUPABASE_SECRET_KEY'];headers={'apikey':secret,'Authorization':'Bearer '+secret}
    for name,body in [(value['version']+'.json',data),('latest.json',json.dumps({'version':value['version'],'updated_at':value['updated_at']}).encode())]:
        r=requests.post(base+'/object/'+BUCKET+'/'+name,headers={**headers,'Content-Type':'application/json','x-upsert':'true','Cache-Control':'no-store'},data=body,timeout=20)
        r.raise_for_status()
    # Retain current and previous snapshots, not a growing historical archive.
    r=requests.post(base+'/object/list/'+BUCKET,headers=headers,json={'prefix':'','limit':1000,'sortBy':{'column':'created_at','order':'desc'}},timeout=10);r.raise_for_status()
    older=[x['name'] for x in r.json() if x.get('name','').endswith('.json') and x['name'] not in ('latest.json',value['version']+'.json')][1:]
    if older:
        r=requests.delete(base+'/object/'+BUCKET,headers=headers,json={'prefixes':older},timeout=10);r.raise_for_status()
    print(json.dumps({'shared_catalog_published':value['version']}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path');publish(p.parse_args().path)
