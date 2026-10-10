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
from concert_discovery.email_ui import unsubscribe_page, preferences as email_preferences
unsubscribe_page()
st.markdown('''<style>.st-key-review_navigation [role="radiogroup"]{gap:8px;border:0;background:transparent;flex-wrap:wrap}.st-key-review_navigation button[data-testid*="segmented_control"]{border-radius:999px!important;border:0!important;padding:8px 16px;background:transparent;color:#526071;min-height:40px;box-shadow:none!important}.st-key-review_navigation button[data-testid*="segmented_control"]:hover{background:#edf3f4;color:#102c43}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"]{background:#102c43!important;color:#fff!important}.st-key-review_navigation button p{font-size:14px;font-weight:600}.st-key-review_navigation button code{font-family:inherit;font-size:11px;border-radius:999px;background:#e6ecef;color:#526071;padding:2px 6px;margin-left:5px}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"] code{background:#ffffff24;color:#d9eee9}.st-key-filter_bar button[data-testid="stPopoverButton"]{border-radius:999px;border:1px solid transparent;background:#f0f4f6;color:#63717d;padding:7px 12px;height:42px;min-height:42px;box-shadow:none}.st-key-filter_bar button[data-testid="stPopoverButton"]:hover{border-color:#b2c8cb;background:#e7f0f1}.st-key-filter_bar button[data-testid="stPopoverButton"] p{font-size:13px}.st-key-filter_bar button[data-testid="stPopoverButton"] strong{color:#102c43;font-weight:600}.st-key-filter_bar [data-testid="stHorizontalBlock"]{gap:8px;flex-wrap:wrap}.st-key-filter_bar [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{flex:0 0 auto!important;width:auto!important;min-width:0!important}.st-key-filter_bar button[data-testid="stPopoverButton"]{width:auto!important}.st-key-filter_bar button[data-testid="stPopoverButton"] p{white-space:nowrap}.st-key-filter_bar [data-testid="stColumn"]:has(.st-key-search_filter){width:220px!important;max-width:100%!important}.st-key-search_filter{width:100%}@media(prefers-color-scheme:dark){.st-key-review_navigation button[data-testid*="segmented_control"]{color:#b7c7d0}.st-key-review_navigation button[data-testid*="segmented_control"]:hover{background:#263d49;color:#fff}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"]{background:#bde6de!important;color:#102c43!important}.st-key-review_navigation button code{background:#314752;color:#c5d6de}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"] code{background:#102c4320;color:#102c43}.st-key-filter_bar button[data-testid="stPopoverButton"]{background:#233843;color:#b5c6ce}.st-key-filter_bar button[data-testid="stPopoverButton"] strong{color:#e4f3ef}.st-key-filter_bar button[data-testid="stPopoverButton"]:hover{background:#2b464d;border-color:#537a7a}}
.st-key-review_navigation{border-bottom:1px solid #e1e7eb;margin-bottom:8px}.st-key-review_navigation button[data-testid*="segmented_control"]{border-radius:0!important;background:transparent!important;padding:10px 4px!important;margin-right:24px;border-bottom:3px solid transparent!important;color:#71808b!important}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"]{color:#102c43!important;border-bottom-color:#102c43!important}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"] code{background:#e6ecef!important;color:#526071!important}
[data-testid=stPopoverBody]:has(.st-key-growth_range){width:300px!important;min-width:0!important;max-width:calc(100vw - 32px)!important}[data-testid=stCheckbox] code{font-family:inherit;font-size:11px;font-weight:600;color:#526071;background:#eef0f3;border-radius:999px;padding:1px 7px;margin-left:6px;white-space:nowrap}.block-container{max-width:1600px;padding-top:2rem}h1{letter-spacing:-1px}.soundcheck-header{width:100vw;margin-left:calc(50% - 50vw);box-sizing:border-box;padding:32px max(5rem,calc((100vw - 1440px)/2));margin-bottom:20px;display:flex;align-items:center;gap:16px}@media(max-width:640px){.soundcheck-header{padding:24px 1rem;gap:12px}.soundcheck-header h1{font-size:1.8rem}.soundcheck-header img{width:60px}}[data-testid="stElementContainer"]:has(iframe[title="shortlist_app.filter_preferences_v1"]){display:none}.st-key-brand_header{position:relative}.st-key-banner_auth{position:absolute;right:0;top:3rem;width:auto;z-index:10}.st-key-banner_auth button{background:#102c43;color:#fff;border-color:#bde6de}@media(max-width:640px){.st-key-banner_auth{top:2rem;right:0}.soundcheck-header h1{max-width:210px}}.st-key-search_filter button [data-testid="stIconMaterial"]{display:none}.st-key-search_filter button::before{content:"";width:18px;height:18px;background:currentColor;mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.3-4.3'/%3E%3C/svg%3E") center/contain no-repeat}</style>''',unsafe_allow_html=True)
with st.container(key='brand_header'):
 logo_data=base64.b64encode((Path(__file__).parent/'assets/soundcheck-logo.png').read_bytes()).decode()
 header_data=base64.b64encode((Path(__file__).parent/'assets/concert-header.jpg').read_bytes()).decode()
 st.markdown(f'<div class="soundcheck-header" style="background:linear-gradient(90deg,rgba(16,44,67,.95),rgba(16,44,67,.45)),url(data:image/jpeg;base64,{header_data}) center 58%/cover"><img src="data:image/png;base64,{logo_data}" width="80" alt=""><div><h1 style="padding:0;margin:0;color:#fff">Asheville Soundcheck</h1><div style="color:#BDE6DE;margin-top:6px">Upcoming Asheville shows</div></div></div>',unsafe_allow_html=True)
 from concert_discovery.accounts import StatusStore,user_key
 from concert_discovery.calendar_links import google_calendar_link
 account_id=None
 status_store=None
 try:auth_configured=bool(st.secrets.get('auth',{}).get('client_id'))
 except FileNotFoundError:auth_configured=False
 if auth_configured:
  if st.user.is_logged_in:
   account_id=user_key(dict(st.user))
   with st.container(key='banner_auth'):
    email_column,sign_column=st.columns([1.6,1])
    with email_column:email_preferences(account_id,auth_configured)
    with sign_column:st.button('Sign out',on_click=st.logout)
   status_store=StatusStore(st.secrets['supabase']['url'],st.secrets['supabase']['secret'])
   if st.session_state.get('status_account')!=account_id:
    try:st.session_state['account_statuses']=status_store.load(account_id)
    except Exception:
     st.error('Account status storage is not ready. Your choices have not been changed.')
     st.stop()
    st.session_state['status_account']=account_id
  else:
   with st.container(key='banner_auth'):
    email_column,sign_column=st.columns([1.6,1])
    with email_column:email_preferences(account_id,auth_configured)
    with sign_column:st.button('Sign in',on_click=st.login)
@st.cache_resource
def prepare_catalog():
 initialize()
prepare_catalog()
@st.cache_data(ttl=15,show_spinner=False)
def cached_catalog():
 return get_shows(user_id='browser-view')
shows=cached_catalog()
venue_labels={'sierra-nevada':'Sierra Nevada','thomas-wolfe':"Harrah's",'harrahs-arena':"Harrah's",'ayurprana':'AyurPrana','oskar-blues-brevard':'Oskar Blues'}
revival_icon='data:image/webp;base64,'+base64.b64encode((Path(__file__).parent/'assets'/'revival.webp').read_bytes()).decode()
for show in shows:
 if show['venue_id']=='revival':show['venue_icon']=revival_icon
 show['venue_name']=venue_labels.get(show['venue_id'],show['venue_name'])
from concert_discovery.reconciliation import key_aliases
if account_id:
 aliases=key_aliases()
 saved=st.session_state.get('account_statuses',{})
 for old,new in aliases.items():
  if old in saved and new not in saved:saved[new]=saved[old]
for show in shows:
 choice=st.session_state.get('account_statuses',{}).get(show['dedupe_key'],'Unread') if account_id else 'Unread'
 show['decision']={'Unread':None,'Pass':'passed','Interested':'interested','Going':'going'}.get(choice)
from concert_discovery.collection_health import warning
@st.cache_data(ttl=60,show_spinner=False)
def cached_health_warning():
 return warning()
health_warning=cached_health_warning()
if health_warning:st.caption('⚠️ '+health_warning)
venues=sorted({s['venue_name'] for s in shows})
from concert_discovery.genre_labels import genre_labels
def show_genres(show):
 return {g for a in show['headliners'] for g in genre_labels(a.get('genre'))} or {'Unknown'}
genres=sorted({g for s in shows for g in show_genres(s)})
from concert_discovery.event_classification import TYPES
show_types=TYPES
status_options=['Unread','Pass','Interested','Going']
status_label=lambda v: {'Unread':'Not Reviewed','Pass':'Hidden'}.get(v,v)
import streamlit.components.v1 as components
preferences_bridge=components.declare_component('filter_preferences_v1',path=str(Path(__file__).parent/'filter_preferences'))
owner=account_id or 'guest'
if st.session_state.get('filter_owner')!=owner:
 for k in list(st.session_state):
  if k.startswith(('venue_','status_','genre_','type_')) and k not in ('status_account',):del st.session_state[k]
 for k in ('listener_range','growth_range','hide_unknown','hide_not_interested','review_view','saved_view','reveal_filtered_saved','last_status_change','filter_preferences','filter_preferences_saved','guest_filters_loaded'):
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
prefs=dict(st.session_state.get('filter_preferences') or {})
# Defaults apply only to missing settings, never overwrite a saved choice.
prefs.setdefault('hide_unknown',True)
prefs.setdefault('excluded_types',[t for t in show_types if t!='Live Music'])
# Merge the old room filters using OR: either selected room keeps the combined venue selected.
if 'excluded_venues' in prefs and prefs.get('venue_grouping_version')!=1:
 old_excluded=set(prefs['excluded_venues'])
 if not {'Thomas Wolfe',"Harrah's Cherokee"}.issubset(old_excluded):old_excluded.discard("Harrah's Cherokee")
 old_excluded.discard('Thomas Wolfe');prefs['excluded_venues']=sorted(old_excluded)
if 'venue_Thomas Wolfe' in st.session_state:
 st.session_state["venue_Harrah's Cherokee"]=st.session_state.get("venue_Harrah's Cherokee",False) or st.session_state.pop('venue_Thomas Wolfe')
venue_renames={"Harrah's Cherokee":"Harrah's",'AyurPrana Listening Room':'AyurPrana','Oskar Blues Brewery':'Oskar Blues'}
prefs['excluded_venues']=[venue_renames.get(v,v) for v in prefs.get('excluded_venues',[])]
for old,new in venue_renames.items():
 if 'venue_'+old in st.session_state:st.session_state['venue_'+new]=st.session_state.pop('venue_'+old)
if not st.session_state.get('filters_initialized') or st.session_state.get('filters_initialized')!=owner:
 for v in venues:st.session_state['venue_'+v]=v not in prefs.get('excluded_venues',[])
 for g in genres:st.session_state['genre_'+g]=g not in prefs.get('excluded_genres',[])
 for v in status_options:st.session_state['status_'+v]=v in prefs.get('statuses',['Unread','Interested','Going'])
 st.session_state['hide_unknown']=prefs.get('hide_unknown',True)
 st.session_state['hide_not_interested']=prefs.get('hide_not_interested','Pass' not in prefs.get('statuses',['Unread','Interested','Going']))
 st.session_state['review_view']='All' if prefs.get('review_view')=='All' else 'To Review'
 st.session_state['saved_view']=prefs.get('saved_view','All saved') if prefs.get('saved_view') in ('All saved','Interested','Going') else 'All saved'
 st.session_state['filters_initialized']=owner

if 'Music' in prefs.get('excluded_types',[]):prefs['excluded_types']=[('Live Music' if t=='Music' else t) for t in prefs['excluded_types']]
for t in show_types:st.session_state.setdefault('type_'+t,t not in prefs.get('excluded_types',[]))
for g in genres:st.session_state.setdefault('genre_'+g,g not in prefs.get('excluded_genres',[]))
for v in venues:st.session_state.setdefault('venue_'+v,True)
for v in status_options:st.session_state.setdefault('status_'+v,v!='Pass')
def set_checks(prefix,items,value):
 for item in items:st.session_state[prefix+item]=value
def selection_label(items,selected):
 return 'All' if len(selected)==len(items) else 'None selected' if not selected else f'{len(selected)} selected'
selected_venues=[v for v in venues if st.session_state['venue_'+v]]
st.session_state.setdefault('hide_not_interested',prefs.get('hide_not_interested',True))
statuses=[v for v in status_options if v!='Pass' or not st.session_state['hide_not_interested']]
upper=max(1000,((max((r['audience'] or 0 for r in shows),default=0)+99999)//100000)*100)
saved_range=prefs.get('listener_range');st.session_state.setdefault('listener_range',tuple(max(0,min(upper,x)) for x in saved_range) if saved_range else (0 if 'listener_range' in prefs else 500,upper))
low_k,high_k=st.session_state['listener_range']
listener_summary='Any' if low_k==0 and high_k==upper else f'≥{low_k:,}k' if high_k==upper else f'≤{high_k:,}k' if low_k==0 else f'{low_k:,}–{high_k:,}k'
if st.session_state.get('hide_unknown',False):listener_summary+=' · Hide unknown'
status_summary=', '.join(status_label(v) for v in statuses) if len(statuses)<4 else 'All'
growth_values=[s['listener_growth_6m'] for s in shows if s['listener_growth_6m'] is not None]
growth_floor=min(-100,math.floor(min(growth_values,default=-100)/10)*10)
growth_ceiling=max(100,math.ceil(max(growth_values,default=100)/10)*10)
saved_growth=prefs.get('growth_range');st.session_state.setdefault('growth_range',tuple(max(growth_floor,min(growth_ceiling,x)) for x in saved_growth) if saved_growth else (growth_floor,growth_ceiling))
growth_low,growth_high=st.session_state['growth_range']
growth_summary='Any' if (growth_low,growth_high)==(growth_floor,growth_ceiling) else f'≥{growth_low:+,}%' if growth_high==growth_ceiling else f'≤{growth_high:+,}%' if growth_low==growth_floor else f'{growth_low:+,}% to {growth_high:+,}%' 
selected_genres=[g for g in genres if st.session_state['genre_'+g]]
selected_types=[t for t in show_types if st.session_state['type_'+t]]
review_navigation=st.container(key='review_navigation')
with st.container(key='filter_bar'):
 cols=st.columns([1.2,1.7,1.3,.9,1.1,.35],gap='small')
# Facet counts reflect the selected review view as well as the taste filters.
from concert_discovery.review_workflow import statuses_for, select_view
if st.session_state.get('review_view') not in ('To Review','All'):st.session_state['review_view']='To Review'
statuses=statuses_for(st.session_state['review_view'])
with cols[5],st.container(key='search_filter'):
 search_component=components.declare_component('artist_search_live_v2',path=str(Path(__file__).parent/'artist_search'))
 artist_search=search_component(value=st.session_state.get('artist_name_search',''),key='artist_search_live',default='') or ''
 st.session_state['artist_name_search']=artist_search
from concert_discovery.filter_counts import counts as facet_counts
option_counts,all_counts=facet_counts(shows,selected_venues,selected_genres,selected_types,statuses,(low_k,high_k),st.session_state.get('hide_unknown',False),(growth_low,growth_high),(growth_floor,growth_ceiling),artist_search,show_genres)
def counted(label,facet,value=None):
 count=all_counts[facet] if value is None else option_counts[facet].get(value,0)
 return label+' `'+str(count)+'`'
with cols[0].popover('**Venues** · '+selection_label(venues,selected_venues),use_container_width=True):
 st.session_state['all_venues_control']=len(selected_venues)==len(venues)
 st.checkbox(counted('All','venue'),key='all_venues_control',on_change=lambda:set_checks('venue_',venues,st.session_state['all_venues_control']))
 st.markdown('<div style="border-top:1px solid #cbd2d9;margin:3px 0 5px"></div>',unsafe_allow_html=True)
 core_ids={'brevard-music-center','asheville-music-hall','one-stop','eulogy','hellbender','grey-eagle','orange-peel','harrahs-arena','thomas-wolfe','sierra-nevada'}
 core_names={s['venue_name'] for s in shows if s['venue_id'] in core_ids}
 st.caption('Core venues · All shows')
 selected_venues=[v for v in venues if v in core_names and st.checkbox(counted(v,'venue',v),key='venue_'+v)]
 st.caption('Other venues · Select shows')
 selected_venues += [v for v in venues if v not in core_names and st.checkbox(counted(v,'venue',v),key='venue_'+v)]
with cols[1].popover('**Spotify Listeners** · '+listener_summary,use_container_width=True):
 low_k,high_k=st.slider("Listeners ('000s)",0,upper,step=50,key='listener_range',help='Values are thousands: 250 = 250k.')
 hide_unknown=st.checkbox("Hide 'unknown'",key='hide_unknown')
 minimum=low_k*1000
with cols[2].popover('**Trending** · '+growth_summary,use_container_width=True):
 growth_low,growth_high=st.slider('Six-month growth (%)',growth_floor,growth_ceiling,step=1,key='growth_range',format='%d%%')
with cols[4].popover('**Genre** · '+selection_label(genres,selected_genres),use_container_width=True):
 st.session_state['all_genres_control']=len(selected_genres)==len(genres)
 st.checkbox(counted('All','genre'),key='all_genres_control',on_change=lambda:set_checks('genre_',genres,st.session_state['all_genres_control']))
 st.markdown('<div style="border-top:1px solid #cbd2d9;margin:3px 0 5px"></div>',unsafe_allow_html=True)
 selected_genres=[g for g in genres if st.checkbox(counted(g,'genre',g),key='genre_'+g)]
with cols[3].popover('**Type** · '+selection_label(show_types,selected_types),use_container_width=True):
 st.session_state['all_types_control']=len(selected_types)==len(show_types)
 st.checkbox(counted('All','type'),key='all_types_control',on_change=lambda:set_checks('type_',show_types,st.session_state['all_types_control']))
 st.markdown('<div style="border-top:1px solid #cbd2d9;margin:3px 0 5px"></div>',unsafe_allow_html=True)
 selected_types=[t for t in show_types if st.checkbox(counted(t,'type',t),key='type_'+t)]
growth_active=(growth_low,growth_high)!=(growth_floor,growth_ceiling)
selected=filter_table(shows,selected_venues,status_options,minimum,growth_low if growth_active else None)
selected=[s for s in selected if show_genres(s).intersection(selected_genres)]
selected=[s for s in selected if ((s.get('event_classification') or {}).get('category') or 'unknown').replace('_',' ').title() in selected_types]
if growth_active:selected=[r for r in selected if r['listener_growth_6m']<=growth_high]
selected=[r for r in selected if (r['audience'] is not None or not hide_unknown) and (r['audience'] is None or r['audience']<=high_k*1000)]
if artist_search.strip():
 query=artist_search.strip().casefold()
 selected=[s for s in selected if query in s['title'].casefold() or any(query in a['display_name'].casefold() for a in s['headliners'])]
matching=selected
view_counts={v:len(select_view(matching,v)) for v in ('To Review','All')}
def retain_selection(key,default):
 if st.session_state.get(key) is None:st.session_state[key]=default
with review_navigation:
 st.segmented_control('Your shows',['To Review','All'],key='review_view',format_func=lambda v:v+' `'+str(view_counts[v])+'`',label_visibility='collapsed',selection_mode='single',on_change=retain_selection,args=('review_view','To Review'))
view=st.session_state['review_view']
selected=select_view(matching,view)
st.caption(f'Showing {len(selected)} of {len(shows)}')
status_error=st.session_state.pop('status_save_error',None)
if status_error:st.error(status_error)
current_preferences={'venue_grouping_version':1,'review_view':view,'saved_view':st.session_state.get('saved_view','All saved'),'excluded_types':[t for t in show_types if t not in selected_types],'excluded_genres':[g for g in genres if g not in selected_genres],'excluded_venues':[v for v in venues if v not in selected_venues],'statuses':statuses,'hide_not_interested':True,'hide_unknown':hide_unknown,'listener_range':None if (low_k,high_k)==(0,upper) else [low_k,high_k],'growth_range':None if (growth_low,growth_high)==(growth_floor,growth_ceiling) else [growth_low,growth_high]}
if account_id and current_preferences!=st.session_state.get('filter_preferences_saved'):
 try:
  status_store.save_filters(account_id,current_preferences)
  st.session_state['filter_preferences_saved']=current_preferences
 except Exception:st.warning('Your filters changed, but could not be saved. Try again shortly.')
st.session_state['filter_preferences']=current_preferences
if not account_id and st.session_state.get('guest_filters_loaded'):
 preferences_bridge(preferences=current_preferences,key='guest_preferences_save',default=None)
calendar_id=None
if account_id:
 calendar_defaults=st.secrets.get('calendar_defaults',{})
 if st.user.get('email')==calendar_defaults.get('owner_email'):
  calendar_id=calendar_defaults.get('calendar_id')
labels={None:'Unread','passed':'Pass','interested':'Interested','going':'Going'}
data=[]
for s in selected:
 a=s['audience_artist']
 headliners=s['headliners']
 from concert_discovery.bill_presentation import name as display_name
 name=display_name(s)
 genre=(a.get('genre') if a else None) or next((h.get('genre') for h in headliners if h.get('genre')),None)
 listen=a['spotify_profile_url'] if a else next((h['spotify_profile_url'] for h in headliners if h['spotify_profile_url']),None)
 image=(a.get('image_url') if a else None) or next((h.get('image_url') for h in headliners if h.get('image_url')),None)
 data.append({'show_id':s['show_id'],'Date':datetime.fromisoformat(s['performance_start']).date(),'Artist image':image,'Name':name,
              'Venue icon':s.get('venue_icon'),'Venue':s['venue_name'],'Genre':', '.join(genre_labels(genre)) if genre else '—','Monthly listeners':compact_audience(s['audience']),
              '6-month growth':s['listener_growth_6m'],'Status':labels.get(s['decision'],'Unread'),'Listen':listen,
              'Buy':s['ticket_url'] or s['official_event_url'] or s['venue_calendar_url']})
if data:
 import streamlit.components.v1 as components
 table=components.declare_component('concert_table_v18',path=str(Path(__file__).parent/'show_table'))
 from concert_discovery.prices import load as load_prices, for_show, label as price_label
 prices=load_prices()
 rows=[]
 for item,show in zip(data,selected):
  price=for_show(show,prices)
  rows.append(dict(id=show['dedupe_key'] if account_id else item['show_id'],date_sort=show['performance_start'],date=item['Date'].strftime('%a %b %d')+(item['Date'].strftime(" '%y") if item['Date'].year!=datetime.now().year else ''),name=item['Name'],artist_image=item['Artist image'],artists=[dict(name=a['display_name'],image=a.get('image_url'),url=a.get('spotify_profile_url')) for a in show['headliners']] if show['event_classification']['category'] in ('live_music','cover_band') else [],
      venue=item['Venue'],venue_icon=item['Venue icon'],show_type=((show.get('event_classification') or {}).get('category') or 'unknown').replace('_',' ').title(),type_evidence=(show.get('event_classification') or {}).get('evidence',''),genre=item['Genre'],listeners=show['audience'],listeners_label=item['Monthly listeners'],
      price=price['min'] if price else None,price_label=price_label(price),price_detail=(f"Advertised price · {price['source']} · checked {price['checked_at']}. Fees may vary by source." if price else ''),
      growth=show['listener_growth_6m'],growth_artist=(show['growth_artist'] or {}).get('display_name'),growth_detail=(show['growth_artist'] or {}).get('growth_detail'),
      just_announced=show.get('just_announced'),sold_out=show.get('sold_out'),status=item['Status'],listen=item['Listen'],buy=item['Buy'],calendar=google_calendar_link(show,item['Name'],item['Buy'],calendar_id),calendar_label='Add to Family Google Calendar' if calendar_id else 'Add to Google Calendar',listener_artist=(show['audience_artist'] or {}).get('display_name'),
      sources=[dict(label=x['source_name'],url=x['source_url']) for x in show['sources']],
      photo_source=(show['audience_artist'] or next(iter(show['headliners']),{})).get('image_source'),
      genre_source=next((h.get('genre_source') for h in ([show['audience_artist']] if show['audience_artist'] and show['audience_artist'].get('genre') else show['headliners']) if h.get('genre')),None),
      match_reason=(show['audience_artist'] or next(iter(show['headliners']),{})).get('match_reason','Unresolved; link opens a name search.')))

 action=table(rows=rows,key='concert_table_'+(account_id or 'guest'),default=None,account_id=account_id,decisions=st.session_state.get('account_statuses',{}) if account_id else None,review_view=view,acknowledged=st.session_state.get('status_acknowledged',[]))
 if action and action.get('event_id')!=st.session_state.get('last_status_event'):
  if action.get('login_requested') and not account_id:
   st.session_state['last_status_event']=action['event_id']
   @st.dialog('Sign in to save your choices')
   def login_prompt():
    if auth_configured:
     left,center,right=st.columns([1,2,1])
     with center:st.button('Sign in with Google',on_click=st.login,key='status_login',use_container_width=True)
    else:st.info('Sign-in is not configured for this app yet.')
   login_prompt()
  elif account_id:
   changes=action.get('changes') or ([action['change']] if action.get('change') else [])
   acknowledged=st.session_state.setdefault('status_acknowledged',[])
   valid_keys={s['dedupe_key'] for s in shows}
   for change in changes:
    token=change.get('token')
    if token in acknowledged:continue
    if change.get('show_key') in valid_keys and change.get('status') in ('Unread','Pass','Interested','Going'):
     try:
      status_store.save(account_id,change['show_key'],change['status'])
      st.session_state['account_statuses'][change['show_key']]=change['status']
     except Exception:
      st.session_state['status_save_error']='Could not save your choice. It has been restored; please try again.'
    if token:acknowledged.append(token)
   st.session_state['status_acknowledged']=acknowledged[-200:]
   st.session_state['last_status_event']=action['event_id']
   if changes:st.rerun()



else:
 if view=='To review' and view_counts['All']:
  st.success('You’re caught up. New matching shows will appear here.')
 elif view=='Saved':st.info('No saved shows here yet. Bookmark a show as Interested or mark it Going.' if account_id else 'Sign in to see your Interested and Going shows.')
 elif view=='Hidden':st.info('No hidden shows match your filters.')
 else:st.info('No shows match your filters. Try more venues or a lower listener minimum.')
st.caption('Six-month growth uses PastSpot dated listener history; multi-artist bills show the highest headliner growth. — means not enough history. No minimum includes shows without audience data. Growth and audience filters work independently.')
with st.expander('Excluded events'):
 from concert_discovery.discovery import excluded_events
 exclusions=excluded_events()
 st.caption('Upcoming stored listings hidden by catalog rules, independent of your filters. Includes duplicates, cancellations and disappeared listings. Events rejected before import are not recorded here.')
 if exclusions:st.dataframe(exclusions,hide_index=True,use_container_width=True,column_config={'Source':st.column_config.LinkColumn('Source')})
 else:st.caption('No stored upcoming exclusions.')
