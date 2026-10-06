"""Evidence-based event classification, independent of Spotify identity."""
import re,json
from concert_discovery.storage import utc_now
EXCLUDED=set()
CATEGORY_LABELS={'music':'live_music','theater':'theatre','market':'events','trivia':'events','wellness':'events','open_mic':'events','storytelling':'events','civic':'events','expo':'events','unknown':'live_music'}
TYPES=['Live Music','Cover Band','Comedy','Sports','Dance','Theatre','Events']
TITLE_RULES=[
 ('events',r'\bkaraoke\b|\bterra?oke\b|\bline danc(?:e|ing)\b|\bgiddy up brunch\b|\bburlesque\b|\b(?:goth|gothic) prom\b|\b(?:gothic )?dance (?:night|party)\b|\bmusic competition\b|\b(?:beer|brew|bottle|can) release\b|\bbeer.{0,25}\breleased?\b|\brelease of our.{0,40}\b(?:ipa|beer|ale)\b|\b(?:beer|brew|bottle|can) (?:launch|party)\b|\b(?:magical )?cirque\b|\b(?:craft|artisan) (?:fair|bazaar)\b|\bmarket\b|\btrivia\b|\byoga\b|\bopen mic\b|\bjam (?:night|session)\b|\b(?:folk|songwriter|community) sessions\b|\bshakedown (?:sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b|\bthe moth\b|\bstoryslam\b|\bjustice forum\b|\bexpo\b'),
 ('cover_band',r'\btribute\b|\bcover band\b|\bcover act\b|\bthe ultimate .{1,60} experience\b|\b(?:love|celebration|recreation) of (?:the )?music of\b|\bbring.{0,80}studio recordings.{0,80}to life\b|\bplays?\s+.{1,80}[’\']s\s+(?:document|album|catalog|songs|music)\b|\bplays?\s+.{1,80}\bcatalog(?:ue)?\b'),
 ('comedy',r'\bcomedy\b|\bcomedian\b|\bstand[- ]up\b'),
 ('sports',r'\bgymnastics\b|\bvolleyball\b|\bbasketball\b|roller derby|\bwrestling\b|october skate party|championship'),
 ('dance',r'\bballet\b|dance theatre|dance competition'),
 ('theatre',r'nutcracker|\btheatre performance\b|\btheater performance\b'),
 ('events',r'\bgala\b')]
def classify(text='',classifications=()):
    # Explicit non-performance format wins over a provider's generic Music segment.
    for category,pattern in TITLE_RULES:
        match=re.search(pattern,text,re.I)
        if match:return category,'Explicit event label: '+match.group()
    for item in classifications or ():
        segment=item.get('segment',{}).get('name','').lower()
        genre=item.get('genre',{}).get('name','').lower()
        if genre in ('dance','ballet'):return 'dance','Structured event genre: '+genre.title()
        if genre in ('theatre','theater'):return 'theatre','Structured event genre: '+genre.title()
        if segment=='sports':return 'sports','Structured event segment: Sports'
        if genre=='comedy':return 'comedy','Structured event genre: Comedy'
        if genre in ('tribute','tribute band','cover band'):return 'cover_band','Structured event genre: '+genre.title()
        if segment=='music':return 'live_music','Structured event segment: Music'
    return 'unknown','No explicit event category'
def schema(c):
    c.execute("CREATE TABLE IF NOT EXISTS show_classifications(show_id INTEGER,source_key TEXT PRIMARY KEY,category TEXT,evidence TEXT,source_url TEXT,observed_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS show_event_states(show_id INTEGER,source_key TEXT PRIMARY KEY,status TEXT,source_url TEXT,observed_at TEXT)")
def save(c,sid,event):
    schema(c)
    category,evidence=classify(event.get('category_text',event['title']),event.get('classifications',()))
    if category in ('unknown','music','live_music'):
        artist_tags={g.strip().casefold() for a in event.get('artist_metadata',{}).values() for g in (a.get('genre') or '').split(',')}
        if artist_tags&{'comedy','comedian'}:category,evidence='comedy','Structured performer genre: Comedy'
        elif artist_tags&{'tribute','tribute band','cover band'}:category,evidence='cover_band','Structured performer genre: Tribute / Cover Band'
    if event.get('category_override'):category,evidence=event['category_override'],event['category_evidence']
    c.execute('INSERT INTO show_classifications VALUES(?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET show_id=excluded.show_id,category=excluded.category,evidence=excluded.evidence,observed_at=excluded.observed_at',(sid,event['source_key'],category,evidence,event['source_url'],utc_now()))
    if event.get('event_status'):
        c.execute('INSERT INTO show_event_states VALUES(?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET show_id=excluded.show_id,status=excluded.status,observed_at=excluded.observed_at',(sid,event['source_key'],event['event_status'],event['source_url'],utc_now()))


def effective(c,table,sid):
 """Official evidence wins; newest observation breaks ties within a source tier."""
 return c.execute('SELECT t.* FROM '+table+" t WHERE show_id=? ORDER BY source_key NOT LIKE '%Official:%',observed_at DESC LIMIT 1",(sid,)).fetchone()

def category_for(c,sid,title):
 rows=c.execute("SELECT * FROM show_classifications WHERE show_id=? AND category!='unknown' ORDER BY source_key NOT LIKE '%Official:%',observed_at DESC",(sid,)).fetchall()
 result=dict(rows[0]) if rows else dict(category=classify(title)[0],evidence=classify(title)[1],source_url=None)
 explicit,reason=classify(title)
 if explicit!='unknown' and (result['category'] in ('unknown','music','live_music') or result['evidence'].startswith(('Explicit calendar label:','Explicit event label:'))):
  result.update(category=explicit,evidence=reason)
 detail=c.execute("SELECT b.* FROM bill_evidence b JOIN show_sources ss USING(source_key) WHERE ss.show_id=? AND b.state='success' AND b.category NOT IN ('unknown','music','live_music') ORDER BY b.checked_at DESC LIMIT 1",(sid,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='bill_evidence'").fetchone() else None
 if detail and result['category'] in ('unknown','music','live_music'):result.update(category=detail['category'],evidence=detail['evidence'],source_url=detail['source_url'])
 series=c.execute("SELECT b.evidence,b.source_url FROM bill_evidence b JOIN show_sources ss USING(source_key) WHERE ss.show_id=? AND b.state='success' AND b.entity_kind='series' LIMIT 1",(sid,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='bill_evidence'").fetchone() else None
 result['recurring_series']=bool(series)
 if series and result['category'] in ('unknown','music','live_music'):result.update(category='events',evidence=series['evidence'],source_url=series['source_url'])
 if c.execute("SELECT 1 FROM sqlite_master WHERE name='event_type_reviews'").fetchone():
  review=c.execute('SELECT category,evidence FROM event_type_reviews WHERE title_key=?',(' '.join(title.casefold().split()),)).fetchone()
  if review:result.update(category=review['category'],evidence=review['evidence'])
 if result['category'] in ('unknown','music','live_music') and c.execute("SELECT 1 FROM sqlite_master WHERE name='artist_entity_types'").fetchone():
  from concert_discovery.spotify_matching import name_key
  entity=c.execute("SELECT evidence FROM artist_entity_types WHERE name_key=? AND kind='series'",(name_key(title),)).fetchone()
  if entity:result.update(category='events',evidence=entity['evidence'],recurring_series=True)
 result['assumed']=result['category']=='unknown'
 result['category']=CATEGORY_LABELS.get(result['category'],result['category'])
 result['validation_state']='needs_review' if result['assumed'] else 'evidence_backed'
 return result
