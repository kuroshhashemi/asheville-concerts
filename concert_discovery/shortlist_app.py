"""Show table, cached artist data, and durable personal statuses."""
import re
import sys, base64, math
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'.auth-deps'))
import pandas as pd
import streamlit as st
from concert_discovery.storage import initialize
from concert_discovery.discovery import get_shows,filter_table,compact_audience,decide

st.set_page_config(page_title='Asheville Soundcheck',page_icon=str(Path(__file__).parent/'assets/soundcheck-logo.png'),layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>.block-container{max-width:1600px;padding-top:2rem}h1{letter-spacing:-1px}.soundcheck-header{width:100vw;margin-left:calc(50% - 50vw);box-sizing:border-box;padding:32px max(5rem,calc((100vw - 1440px)/2));margin-bottom:20px;display:flex;align-items:center;gap:16px}@media(max-width:640px){.soundcheck-header{padding:24px 1rem;gap:12px}.soundcheck-header h1{font-size:1.8rem}.soundcheck-header img{width:60px}}</style>''',unsafe_allow_html=True)
logo_data=base64.b64encode((Path(__file__).parent/'assets/soundcheck-logo.png').read_bytes()).decode()
header_data=base64.b64encode((Path(__file__).parent/'assets/concert-header.jpg').read_bytes()).decode()
st.markdown(f'<div class="soundcheck-header" style="background:linear-gradient(90deg,rgba(16,44,67,.95),rgba(16,44,67,.45)),url(data:image/jpeg;base64,{header_data}) center 58%/cover"><img src="data:image/png;base64,{logo_data}" width="80" alt=""><div><h1 style="padding:0;margin:0;color:#fff">Asheville Soundcheck</h1><div style="color:#BDE6DE;margin-top:6px">Upcoming Asheville shows</div></div></div>',unsafe_allow_html=True)
from concert_discovery.accounts import StatusStore,user_key
account_id=None
status_store=None
try:auth_configured=bool(st.secrets.get('auth',{}).get('client_id'))
except FileNotFoundError:auth_configured=False
if auth_configured:
 if st.user.is_logged_in:
  account_id=user_key(dict(st.user))
  st.caption('Signed in as '+st.user.get('name','Google user'))
  st.button('Sign out',on_click=st.logout)
  status_store=StatusStore(st.secrets['supabase']['url'],st.secrets['supabase']['secret'])
  if st.session_state.get('status_account')!=account_id:
   try:st.session_state['account_statuses']=status_store.load(account_id)
   except Exception:
    st.error('Account status storage is not ready. Your choices have not been changed.')
    st.stop()
   st.session_state['status_account']=account_id
 else:
  st.button('Sign in with Google',on_click=st.login)
  st.caption('Browse freely. Sign in with Google to mark shows Not Interested, Interested or Going.')
initialize()
shows=get_shows(user_id='browser-view')
venue_labels={'sierra-nevada':'Sierra Nevada','thomas-wolfe':'Thomas Wolfe','harrahs-arena':"Harrah's Cherokee"}
revival_icon='data:image/webp;base64,'+base64.b64encode((Path(__file__).parent/'assets'/'revival.webp').read_bytes()).decode()
for show in shows:
 if show['venue_id']=='revival':show['venue_icon']=revival_icon
 show['venue_name']=venue_labels.get(show['venue_id'],show['venue_name'])
for show in shows:
 choice=st.session_state.get('account_statuses',{}).get(show['dedupe_key'],'Unread') if account_id else 'Unread'
 show['decision']={'Unread':None,'Pass':'passed','Interested':'interested','Going':'going'}.get(choice)
venues=sorted({s['venue_name'] for s in shows})
status_options=['Unread','Pass','Interested','Going']
status_label=lambda v: {'Unread':'Not Reviewed','Pass':'Not Interested'}.get(v,v)
import streamlit.components.v1 as components
preferences_bridge=components.declare_component('filter_preferences_v1',path=str(Path(__file__).parent/'filter_preferences'))
owner=account_id or 'guest'
if st.session_state.get('filter_owner')!=owner:
 for k in list(st.session_state):
  if k.startswith(('venue_','status_')) and k not in ('status_account',):del st.session_state[k]
 for k in ('listener_range','growth_range','hide_unknown','filter_preferences','filter_preferences_saved','guest_filters_loaded'):
  st.session_state.pop(k,None)
 st.session_state['filter_owner']=owner
 if account_id:
  try:st.session_state['filter_preferences']=status_store.load_filters(account_id)
  except Exception:
   st.error('Could not load your saved filters. Please reload to try again.');st.stop()
  st.session_state['filter_preferences_saved']=st.session_state.get('filter_preferences')
if not account_id:
 loaded_preferences=preferences_bridge(preferences=st.session_state.get('filter_preferences') if st.session_state.get('guest_filters_loaded') else None,key='guest_preferences',default=None)
 if loaded_preferences is not None and not st.session_state.get('guest_filters_loaded'):
  st.session_state['filter_preferences']=loaded_preferences.get('preferences')
  st.session_state['guest_filters_loaded']=True
  st.session_state.pop('filters_initialized',None)
prefs=st.session_state.get('filter_preferences') or {}
if not st.session_state.get('filters_initialized') or st.session_state.get('filters_initialized')!=owner:
 for v in venues:st.session_state['venue_'+v]=v not in prefs.get('excluded_venues',[])
 for v in status_options:st.session_state['status_'+v]=v in prefs.get('statuses',['Unread','Interested','Going'])
 st.session_state['hide_unknown']=prefs.get('hide_unknown',bool(account_id))
 st.session_state['filters_initialized']=owner

for v in venues:st.session_state.setdefault('venue_'+v,True)
for v in status_options:st.session_state.setdefault('status_'+v,v!='Pass')
def set_checks(prefix,items,value):
 for item in items:st.session_state[prefix+item]=value
def selection_label(items,selected):
 return 'All selected' if len(selected)==len(items) else 'None selected' if not selected else f'{len(selected)} selected'
selected_venues=[v for v in venues if st.session_state['venue_'+v]]
statuses=[v for v in status_options if st.session_state['status_'+v]]
upper=max(1000,((max((r['audience'] or 0 for r in shows),default=0)+99999)//100000)*100)
saved_range=prefs.get('listener_range');st.session_state.setdefault('listener_range',tuple(max(0,min(upper,x)) for x in saved_range) if saved_range else (0,upper))
low_k,high_k=st.session_state['listener_range']
listener_summary='Any' if low_k==0 and high_k==upper else f'≥{low_k:,}k' if high_k==upper else f'≤{high_k:,}k' if low_k==0 else f'{low_k:,}–{high_k:,}k'
if st.session_state.get('hide_unknown',False):listener_summary+=' · known only'
status_summary=', '.join(status_label(v) for v in statuses) if len(statuses)<4 else 'All selected'
growth_values=[s['listener_growth_6m'] for s in shows if s['listener_growth_6m'] is not None]
growth_floor=min(-100,math.floor(min(growth_values,default=-100)/10)*10)
growth_ceiling=max(100,math.ceil(max(growth_values,default=100)/10)*10)
saved_growth=prefs.get('growth_range');st.session_state.setdefault('growth_range',tuple(max(growth_floor,min(growth_ceiling,x)) for x in saved_growth) if saved_growth else (growth_floor,growth_ceiling))
growth_low,growth_high=st.session_state['growth_range']
growth_summary='Any' if (growth_low,growth_high)==(growth_floor,growth_ceiling) else f'≥{growth_low:+,}%' if growth_high==growth_ceiling else f'≤{growth_high:+,}%' if growth_low==growth_floor else f'{growth_low:+,}% to {growth_high:+,}%' 
cols=st.columns([1.2,1.3,1.4,1.1])
with cols[0].popover('Venues · '+selection_label(venues,selected_venues),use_container_width=True):
 st.session_state['all_venues_control']=len(selected_venues)==len(venues)
 st.checkbox('All venues',key='all_venues_control',on_change=lambda:set_checks('venue_',venues,st.session_state['all_venues_control']))
 core_ids={'asheville-music-hall','one-stop','eulogy','hellbender','grey-eagle','orange-peel','harrahs-arena','thomas-wolfe','sierra-nevada'}
 core_names={s['venue_name'] for s in shows if s['venue_id'] in core_ids}
 st.caption('Core venues · full-calendar coverage target')
 selected_venues=[v for v in venues if v in core_names and st.checkbox(v,key='venue_'+v)]
 st.caption('Other venues · additional shows from our sources')
 selected_venues += [v for v in venues if v not in core_names and st.checkbox(v,key='venue_'+v)]
with cols[1].popover('Spotify Listeners · '+listener_summary,use_container_width=True):
 low_k,high_k=st.slider('Listener range (k)',0,upper,step=50,key='listener_range',help='Values are thousands: 250 = 250k.')
 hide_unknown=st.checkbox('Hide unknown listener counts',key='hide_unknown')
 minimum=low_k*1000
with cols[3].popover('Status · '+(status_summary or 'None selected'),use_container_width=True):
 st.session_state['all_statuses_control']=len(statuses)==len(status_options)
 st.checkbox('All statuses',key='all_statuses_control',on_change=lambda:set_checks('status_',status_options,st.session_state['all_statuses_control']))
 statuses=[v for v in status_options if st.checkbox(status_label(v),key='status_'+v)]
with cols[2].popover('6-month growth · '+growth_summary,use_container_width=True):
 growth_low,growth_high=st.slider('Six-month listener growth (%)',growth_floor,growth_ceiling,step=1,key='growth_range',format='%d%%')
 st.caption('The full range includes unknown growth. Narrow the range to show measured growth only.')
current_preferences={'excluded_venues':[v for v in venues if v not in selected_venues],'statuses':statuses,'hide_unknown':hide_unknown,'listener_range':None if (low_k,high_k)==(0,upper) else [low_k,high_k],'growth_range':None if (growth_low,growth_high)==(growth_floor,growth_ceiling) else [growth_low,growth_high]}
if account_id and current_preferences!=st.session_state.get('filter_preferences_saved'):
 try:
  status_store.save_filters(account_id,current_preferences)
  st.session_state['filter_preferences_saved']=current_preferences
 except Exception:st.warning('Your filters changed, but could not be saved. Try again shortly.')
st.session_state['filter_preferences']=current_preferences
if not account_id and st.session_state.get('guest_filters_loaded'):
 preferences_bridge(preferences=current_preferences,key='guest_preferences_save',default=None)
growth_active=(growth_low,growth_high)!=(growth_floor,growth_ceiling)
selected=filter_table(shows,selected_venues,statuses,minimum,growth_low if growth_active else None)
if growth_active:selected=[r for r in selected if r['listener_growth_6m']<=growth_high]
selected=[r for r in selected if (r['audience'] is not None or not hide_unknown) and (r['audience'] is None or r['audience']<=high_k*1000)]
st.caption(f'{len(selected)} shown of {len(shows)} upcoming records · '+('Change Status to save your choice.' if account_id else 'Sign in with Google to change show statuses.'))
with st.expander('Sources and logic'):
 if selected:
  detail_id=st.selectbox('Show', [r['show_id'] for r in selected],format_func=lambda i: next(r['performance_start'][:10]+' · '+r['title']+' · '+r['venue_name'] for r in selected if r['show_id']==i))
  detail=next(r for r in selected if r['show_id']==detail_id)
  st.markdown('**Show listings:** '+', '.join(f"[{x['source_name']}]({x['source_url']})" for x in detail['sources']))
  artist=detail['audience_artist'] or next(iter(detail['headliners']),{})
  st.markdown('**Artist photo:** '+(f"[Spotify]({artist.get('image_source')})" if artist.get('image_url') else 'Not collected'))
  st.markdown('**Genre:** '+(f"[{artist.get('genre')}]({artist.get('genre_source')})" if artist.get('genre_source') else 'Unavailable'))
  st.markdown('**Spotify link:** '+(f"[Profile]({artist['spotify_profile_url']})" if artist.get('spotify_profile_url') else 'Name search; unresolved'))
  st.caption(artist.get('match_reason',''))
  growth_artist=detail.get('growth_artist')
  if growth_artist and growth_artist.get('growth_detail'):
   g=growth_artist['growth_detail']
   st.markdown(f"**Six-month growth:** {growth_artist['display_name']} · {g['value']:+.1f}% · [PastSpot]({g['source_url']}) · {g['baseline_date']} to {g['latest_date']}")
  from concert_discovery.storage import connect
  from concert_discovery.source_links import schema
  with connect() as evidence_db:
   schema(evidence_db)
   evidence=[dict(r) for r in evidence_db.execute('SELECT spotify_id,source_url,method FROM spotify_source_candidates WHERE artist_id=?',(artist.get('artist_id'),))]
  if evidence:
   st.markdown('**Source-provided Spotify candidates:** '+', '.join(f"[{r['method']}]({r['source_url']}) → [profile](https://open.spotify.com/artist/{r['spotify_id']})" for r in evidence))
   if len({r['spotify_id'] for r in evidence})>1:st.caption('Conflicting profiles retained for review; no automatic replacement.')
  ticket=detail['ticket_url'] or detail['official_event_url'] or detail['venue_calendar_url']
  st.markdown(f'**Ticket link:** [Chosen destination]({ticket})')
  st.caption('Venue/date/bill records combined; official details preferred. Ticket link falls back to event page, then venue calendar. Exact winning ticket source was not separately recorded.')
labels={None:'Unread','passed':'Pass','interested':'Interested','going':'Going'}
data=[]
for s in selected:
 a=s['audience_artist']
 headliners=s['headliners']
 name=' & '.join(dict.fromkeys(h['display_name'] for h in headliners)) if headliners else s['title']
 genre=(a.get('genre') if a else None) or next((h.get('genre') for h in headliners if h.get('genre')),None)
 listen=a['spotify_profile_url'] if a else next((h['spotify_profile_url'] for h in headliners if h['spotify_profile_url']),None)
 image=(a.get('image_url') if a else None) or next((h.get('image_url') for h in headliners if h.get('image_url')),None)
 data.append({'show_id':s['show_id'],'Date':datetime.fromisoformat(s['performance_start']).date(),'Artist image':image,'Name':name,
              'Venue icon':s.get('venue_icon'),'Venue':s['venue_name'],'Genre':re.sub(r'\bEdm\b','EDM',genre.title()) if genre else '—','Monthly listeners':compact_audience(s['audience']),
              '6-month growth':s['listener_growth_6m'],'Status':labels.get(s['decision'],'Unread'),'Listen':listen or 'https://open.spotify.com/search/'+quote(name),
              'Buy':s['ticket_url'] or s['official_event_url'] or s['venue_calendar_url']})
if data:
 import streamlit.components.v1 as components
 table=components.declare_component('concert_table_v13',path=str(Path(__file__).parent/'show_table'))
 rows=[]
 for item,show in zip(data,selected):
  rows.append(dict(id=show['dedupe_key'] if account_id else item['show_id'],date_sort=show['performance_start'],date=item['Date'].strftime('%a %b %d'+(' %Y' if item['Date'].year!=datetime.now().year else '')),name=item['Name'],artist_image=item['Artist image'],artists=[dict(name=a['display_name'],image=a.get('image_url'),url=a.get('spotify_profile_url')) for a in show['headliners']],
      venue=item['Venue'],venue_icon=item['Venue icon'],genre=item['Genre'],listeners=show['audience'],listeners_label=item['Monthly listeners'],
      growth=show['listener_growth_6m'],growth_artist=(show['growth_artist'] or {}).get('display_name'),growth_detail=(show['growth_artist'] or {}).get('growth_detail'),
      status=item['Status'],listen=item['Listen'],buy=item['Buy'],listener_artist=(show['audience_artist'] or {}).get('display_name'),
      sources=[dict(label=x['source_name'],url=x['source_url']) for x in show['sources']],
      photo_source=(show['audience_artist'] or next(iter(show['headliners']),{})).get('image_source'),
      genre_source=next((h.get('genre_source') for h in ([show['audience_artist']] if show['audience_artist'] and show['audience_artist'].get('genre') else show['headliners']) if h.get('genre')),None),
      match_reason=(show['audience_artist'] or next(iter(show['headliners']),{})).get('match_reason','Unresolved; link opens a name search.')))

 action=table(rows=rows,key='concert_table_'+(account_id or 'guest'),default=None,account_id=account_id,decisions=st.session_state.get('account_statuses',{}) if account_id else None)
 if action and action.get('event_id')!=st.session_state.get('last_status_event'):
  if account_id:
   change=action.get('change')
   if change and change.get('show_key') in {s['dedupe_key'] for s in shows} and change.get('status') in ('Unread','Pass','Interested','Going'):
    try:
     status_store.save(account_id,change['show_key'],change['status'])
     st.session_state['account_statuses'][change['show_key']]=change['status']
     st.session_state['last_status_event']=action['event_id']
     st.rerun()
    except Exception:st.error('Could not save your status. Please try again.')


else:
 st.info('No shows match these filters. Select more venues or statuses, or choose No minimum.')
st.caption('Six-month growth uses PastSpot dated listener history; multi-artist bills show the highest headliner growth. — means not enough history. No minimum includes shows without audience data. Growth and audience filters work independently.')
with st.expander('Data notes'):
 st.write('Genre labels come from available event sources and earlier verified artist records. Artist mappings are source-backed candidates unless manually confirmed. Audience uses the largest measured headliner on each bill; an unknown co-headliner may have a larger audience.')
 st.write('Official calendars cover Music Hall, One Stop, Grey Eagle, Orange Peel, Hellbender, Harrah’s arena, and Thomas Wolfe Auditorium. Eulogy uses its linked DICE calendar. Sierra Nevada uses public Songkick listings for Mills River. Coverage can still be incomplete.')
 st.write('Sign in with Google to change show statuses and sync them across devices. Guest filters save in this browser.')

