"""Conservative punctuation normalization, retaining independently linked identities."""
import unicodedata
from concert_discovery.storage import connect

def key(name):
    return ' '.join(unicodedata.normalize('NFKC',name).casefold().translate(str.maketrans({'’':"'",'‘':"'",'ʼ':"'",'`':"'"})).split())

def reconcile(db_path=None):
    merged=[];conflicts=[]
    with connect(db_path) as c:
        groups={}
        for a in c.execute('SELECT * FROM artists'):groups.setdefault(key(a['display_name']),[]).append(dict(a))
        for group in groups.values():
            if len(group)<2:continue
            profiles={a['spotify_artist_id'] for a in group if a['spotify_artist_id']}
            if len(profiles)>1:conflicts.append([a['artist_id'] for a in group]);continue
            group.sort(key=lambda a:(not bool(a['spotify_artist_id']),a['match_status'] not in ('manual_confirmed','source_link'),a['artist_id']))
            winner=group[0]['artist_id']
            for a in group[1:]:
                loser=a['artist_id']
                for table in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='artists'")]:
                    cols=[r[1] for r in c.execute('PRAGMA table_info("'+table+'")')]
                    if 'artist_id' not in cols:continue
                    # Update in place: snapshot IDs must survive migration unchanged.
                    # Keep colliding metadata as durable audit evidence before merging.
                    import json
                    c.execute('CREATE TABLE IF NOT EXISTS artist_merge_evidence(loser TEXT,winner TEXT,table_name TEXT,payload TEXT)')
                    for row in c.execute('SELECT * FROM "'+table+'" WHERE artist_id=?',(loser,)).fetchall():
                        c.execute('INSERT INTO artist_merge_evidence VALUES(?,?,?,?)',(loser,winner,table,json.dumps(dict(row))))
                    c.execute('UPDATE OR IGNORE "'+table+'" SET artist_id=? WHERE artist_id=?',(winner,loser))
                    c.execute('DELETE FROM "'+table+'" WHERE artist_id=?',(loser,))
                c.execute('DELETE FROM artists WHERE artist_id=?',(loser,));merged.append((loser,winner))
    return {'merged':merged,'conflicts':conflicts}
