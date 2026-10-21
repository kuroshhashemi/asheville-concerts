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

st.set_option('client.toolbarMode','minimal')
st.set_page_config(page_title='Asheville Soundcheck',page_icon=str(Path(__file__).parent/'assets/soundcheck-logo.png'),layout='wide',initial_sidebar_state='collapsed')
from concert_discovery.email_ui import unsubscribe_page, preferences as email_preferences
unsubscribe_page()
st.markdown('''<style>[data-testid="stHeader"]{display:none}.block-container{padding-top:0!important}.st-key-review_navigation [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:24px;align-items:center}.st-key-review_navigation [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:first-child{flex:0 0 auto!important;width:auto!important;min-width:0!important}.st-key-review_navigation [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]:last-child{flex:1 1 420px!important;min-width:0!important}.st-key-review_guide [data-testid="stMarkdownContainer"]{margin-bottom:0!important}.st-key-review_guide p{font-size:13px;color:#63717d;margin:0;line-height:1.5}.st-key-review_guide strong{font-weight:600;color:#526071}@media(prefers-color-scheme:dark){.st-key-review_guide p{color:#b5c6ce}.st-key-review_guide strong{color:#e4f3ef}}.st-key-review_navigation [role="radiogroup"]{gap:8px;border:0;background:transparent;flex-wrap:wrap}.st-key-review_navigation button[data-testid*="segmented_control"]{border-radius:999px!important;border:0!important;padding:8px 16px;background:transparent;color:#526071;min-height:40px;box-shadow:none!important}.st-key-review_navigation button[data-testid*="segmented_control"]:hover{background:#edf3f4;color:#102c43}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"]{background:#102c43!important;color:#fff!important}.st-key-review_navigation button p{font-size:14px;font-weight:600}.st-key-review_navigation button code{font-family:inherit;font-size:11px;border-radius:999px;background:#e6ecef;color:#526071;padding:2px 6px;margin-left:5px}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"] code{background:#ffffff24;color:#d9eee9}.st-key-filter_bar button[data-testid="stPopoverButton"]{border-radius:999px;border:1px solid transparent;background:#f0f4f6;color:#63717d;padding:7px 12px;height:42px;min-height:42px;box-shadow:none}.st-key-filter_bar button[data-testid="stPopoverButton"]:hover{border-color:#b2c8cb;background:#e7f0f1}.st-key-filter_bar button[data-testid="stPopoverButton"] p{font-size:13px}.st-key-filter_bar button[data-testid="stPopoverButton"] strong{color:#102c43;font-weight:600}.st-key-filter_bar [data-testid="stHorizontalBlock"]{gap:8px;flex-wrap:wrap}.st-key-filter_bar [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{flex:0 0 auto!important;width:auto!important;min-width:0!important}.st-key-filter_bar button[data-testid="stPopoverButton"]{width:auto!important}.st-key-filter_bar button[data-testid="stPopoverButton"] p{white-space:nowrap}.st-key-filter_bar [data-testid="stColumn"]:has(.st-key-search_filter){width:220px!important;max-width:100%!important}.st-key-search_filter{width:100%}@media(prefers-color-scheme:dark){.st-key-review_navigation button[data-testid*="segmented_control"]{color:#b7c7d0}.st-key-review_navigation button[data-testid*="segmented_control"]:hover{background:#263d49;color:#fff}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"]{background:#bde6de!important;color:#102c43!important}.st-key-review_navigation button code{background:#314752;color:#c5d6de}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"] code{background:#102c4320;color:#102c43}.st-key-filter_bar button[data-testid="stPopoverButton"]{background:#233843;color:#b5c6ce}.st-key-filter_bar button[data-testid="stPopoverButton"] strong{color:#e4f3ef}.st-key-filter_bar button[data-testid="stPopoverButton"]:hover{background:#2b464d;border-color:#537a7a}}
.st-key-review_navigation{border-bottom:1px solid #e1e7eb;margin-bottom:8px}.st-key-review_navigation button[data-testid*="segmented_control"]{border-radius:0!important;background:transparent!important;padding:10px 4px!important;margin-right:24px;border-bottom:3px solid transparent!important;color:#71808b!important}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"]{color:#102c43!important;border-bottom-color:#102c43!important}.st-key-review_navigation button[data-testid="stBaseButton-segmented_controlActive"] code{background:#e6ecef!important;color:#526071!important}
[data-testid=stPopoverBody]:has(.st-key-growth_range){width:300px!important;min-width:0!important;max-width:calc(100vw - 32px)!important}[data-testid=stCheckbox] code{font-family:inherit;font-size:11px;font-weight:600;color:#526071;background:#eef0f3;border-radius:999px;padding:1px 7px;margin-left:6px;white-space:nowrap}.block-container{max-width:1600px;padding-top:2rem}h1{letter-spacing:-1px}.soundcheck-header{width:100vw;margin-left:calc(50% - 50vw);box-sizing:border-box;padding:32px max(5rem,calc((100vw - 1440px)/2));margin-bottom:20px;display:flex;align-items:center;gap:16px}@media(max-width:640px){.soundcheck-header{padding:24px 1rem;gap:12px}.soundcheck-header h1{font-size:1.8rem}.soundcheck-header img{width:60px}}[data-testid="stElementContainer"]:has(iframe[title="shortlist_app.filter_preferences_v1"]){display:none}.st-key-brand_header{position:relative}.st-key-banner_auth{position:absolute;right:0;top:3rem;width:auto;z-index:10}.st-key-banner_auth button{background:#102c43;color:#fff;border-color:#bde6de}@media(max-width:640px){.st-key-banner_auth{top:2rem;right:0}.soundcheck-header h1{max-width:210px}}.st-key-search_filter button [data-testid="stIconMaterial"]{display:none}.st-key-search_filter button::before{content:"";width:18px;height:18px;background:currentColor;mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.3-4.3'/%3E%3C/svg%3E") center/contain no-repeat}.st-key-filter_bar [data-testid="stColumn"]:has(.st-key-weekly_email_control){margin-left:auto!important;width:176px!important}.st-key-weekly_email_control button{border:1px solid #b2c8cb!important;background:#eef7f5!important}</style>''',unsafe_allow_html=True)
def dismiss_login():
 st.session_state['login_intro_seen']=True
 st.session_state.pop('login_prompt_requested',None)
 st.query_params.pop('preview_signin',None)
def request_login(arrival=False):
 st.session_state['login_prompt_requested']='arrival' if arrival else 'save'
def login_prompt(arrival=False):
 @st.dialog('Welcome' if arrival else 'Sign In to Save',on_dismiss=dismiss_login)
 def show_prompt():
  st.markdown('<style>[data-testid=stDialog] .st-key-google_signin_popup button{background:#102c43!important;color:white!important;border:0!important;border-radius:999px!important;gap:8px!important}[data-testid=stDialog] .st-key-google_signin_popup button p{color:white!important}[data-testid=stDialog] button{border-radius:999px!important}[data-testid=stDialog] h2{width:100%;text-align:center}[role=dialog] [style*="font-size: 1.5rem"]>div{width:100%}[role=dialog] [style*="font-size: 1.5rem"] p{text-align:center}</style>',unsafe_allow_html=True)
  st.write('Sign in to bookmark/hide shows, get emails about new shows, or save filters')
  with st.container(key='google_signin_popup'):
   st.button('Sign In',on_click=st.login,key='popup_google_signin',width='stretch')
  import streamlit.components.v1 as dialog_components
  dialog_components.html('''<script>
  const doc=parent.document;
  if(!parent.soundcheckBrowseDismiss){
   parent.soundcheckBrowseDismiss=true;
   doc.addEventListener('click',e=>{
    const b=e.target.closest('button');
    if(!b||b.textContent.trim()!=='Browse without sign in')return;
    const dialog=b.closest('[data-testid="stDialog"]')||b.closest('[data-baseweb="modal"]');
    if(dialog)dialog.style.visibility='hidden';
   },true);
  }
  </script>''',height=0)
  if st.button('Browse without sign in',key='browse_without_signin',width='stretch'):
   dismiss_login();st.rerun()
 show_prompt()
st.markdown('<style>[data-stale=true]:has(iframe[title*="concert_table"]){opacity:1!important}[data-testid="stDialog"] [role="dialog"]{position:fixed!important;top:50%!important;left:50%!important;transform:translate(-50%,-50%)!important;margin:0!important;border-radius:24px!important}.st-key-banner_auth button,.st-key-google_signin_popup button,.st-key-weekly_email_control button{border-radius:999px!important}.st-key-google_signin_popup button::before{content:"";width:18px;height:18px;background:url(https://www.google.com/favicon.ico) center/contain no-repeat}.st-key-google_signin_popup button{background:#102c43;color:white;height:42px}</style>',unsafe_allow_html=True)
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
   status_store=StatusStore(st.secrets['supabase']['url'],st.secrets['supabase']['secret'])
   from concert_discovery.activity import ActivityStore
   import time
   activity_store=ActivityStore(st.secrets['supabase']['url'],st.secrets['supabase']['secret'])
   if time.time()-st.session_state.get('activity_touch_'+account_id,0)>=300:
    try:
     activity_store.touch(account_id,dict(st.user))
     st.session_state['activity_touch_'+account_id]=time.time()
    except Exception:
     st.session_state['activity_touch_'+account_id]=time.time()-240

   if st.session_state.get('status_account')!=account_id:
    try:st.session_state['account_statuses']=status_store.load(account_id)
    except Exception:
     st.error('Account status storage is not ready. Your choices have not been changed.')
     st.stop()
    st.session_state['status_account']=account_id
 from concert_discovery.header_controls import render as render_header_controls
 render_header_controls(auth_configured,request_login)
@st.cache_resource
def prepare_catalog():
 initialize()
prepare_catalog()
@st.cache_data(ttl=15,show_spinner=False)
def cached_catalog():
 return get_shows(user_id='browser-view')
shows=cached_catalog()
venue_labels={'sierra-nevada':'Sierra Nevada','thomas-wolfe':"Harrah's",'harrahs-arena':"Harrah's",'ayurprana':'AyurPrana','oskar-blues-brevard':'Oskar Blues'}
for show in shows:
 show['venue_name']=venue_labels.get(show['venue_id'],show['venue_name'])
 if show['venue_id']=='pulp':
  show['venue_name']='The Orange Peel'
  show['venue_icon']=next((s.get('venue_icon') for s in shows if s['venue_id']=='orange-peel'),show.get('venue_icon'))
from concert_discovery.reconciliation import key_aliases
aliases=key_aliases() if account_id else {}
if account_id:
 saved=st.session_state.get('account_statuses',{})
 for old,new in aliases.items():
  if old in saved and new not in saved:saved[new]=saved[old]
# OAuth creates a new session. A tab-scoped bridge carries only the explicit requested action.
import streamlit.components.v1 as components
resume_bridge=components.declare_component('login_action_bridge_v1',path=str(Path(__file__).parent/'login_action_bridge'))
st.markdown('<style>[data-testid="stElementContainer"]:has(iframe[title*="login_action_bridge"]){display:none}</style>',unsafe_allow_html=True)
login_intent=resume_bridge(signed_in=bool(account_id),acknowledged=st.session_state.get('login_intent_ack'),key='login_action_bridge',default=None)
if account_id and isinstance(login_intent,dict) and login_intent.get('token')!=st.session_state.get('login_intent_ack'):
 from concert_discovery.login_actions import validate,apply
 change=validate(login_intent,{s['dedupe_key'] for s in shows},aliases)
 if change:
  try:apply(change,status_store,account_id,st.session_state['account_statuses'])
  except Exception:st.session_state['status_save_error']='Sign-in worked, but your show choice could not be saved. Please click it again.'
 st.session_state['login_intent_ack']=login_intent.get('token')
 st.rerun()
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
from concert_discovery.client_preferences import normalize, VIEWS
upper=max(1000,((max((r['audience'] or 0 for r in shows),default=0)+99999)//100000)*100)
growth_values=[s['listener_growth_6m'] for s in shows if s['listener_growth_6m'] is not None]
growth_floor=min(-100,math.floor(min(growth_values,default=-100)/10)*10)
growth_ceiling=max(100,math.ceil(max(growth_values,default=100)/10)*10)
limits={'listeners':upper,'growth':[growth_floor,growth_ceiling]}
if 'listener_range' not in prefs:prefs['listener_range']=[500,upper]
if 'Music' in prefs.get('excluded_types',[]):prefs['excluded_types']=[('Live Music' if t=='Music' else t) for t in prefs['excluded_types']]
if st.session_state.get('live_filter_owner')!=owner:
 st.session_state['live_filter_owner']=owner
 st.session_state['live_filter_revision']=0
 st.session_state.pop('live_filter_preferences',None)
initial_preferences=normalize(prefs,venues,genres,show_types,upper,limits['growth'])
# A late guest-settings load may update the initial view only before the first interaction.
if not st.session_state.get('live_filter_revision'):
 st.session_state['live_filter_preferences']=initial_preferences

calendar_id=None
if account_id:
 calendar_defaults=st.secrets.get('calendar_defaults',{})
 if st.user.get('email')==calendar_defaults.get('owner_email'):
  calendar_id=calendar_defaults.get('calendar_id')
labels={None:'Unread','passed':'Pass','interested':'Interested','going':'Going'}
data=[]
for s in shows:
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

import streamlit.components.v1 as components
table=components.declare_component('concert_table_v25',path=str(Path(__file__).parent/'show_table'))
from concert_discovery.prices import load as load_prices, for_show, label as price_label
prices=load_prices()
rows=[]
for item,show in zip(data,shows):
 price=for_show(show,prices)
 rows.append(dict(show_key=show['dedupe_key'],id=show['dedupe_key'] if account_id else item['show_id'],date_sort=show['performance_start'],date=item['Date'].strftime('%a %b %d')+(item['Date'].strftime(" '%y") if item['Date'].year!=datetime.now().year else ''),name=item['Name'],artist_image=item['Artist image'],artists=[dict(name=a['display_name'],image=a.get('image_url'),url=a.get('spotify_profile_url')) for a in show['headliners']] if show['event_classification']['category'] in ('live_music','cover_band') else [],
     genre_options=sorted(show_genres(show)),search_text=' '.join([show['title']]+[a['display_name'] for a in show['headliners']]),venue=item['Venue'],venue_icon=item['Venue icon'],show_type=((show.get('event_classification') or {}).get('category') or 'unknown').replace('_',' ').title(),type_evidence=(show.get('event_classification') or {}).get('evidence',''),genre=item['Genre'],listeners=show['audience'],listeners_label=item['Monthly listeners'],
     resale_only=bool(price and price.get('resale_only')),price=price['min'] if price else None,price_label=price_label(price),price_detail=(f"Advertised price · {price.get('source','Structured event data')} · checked {price.get('checked_at',price.get('observed_at',''))}. {'Includes provider-stated fees.' if price.get('includes_fees') else 'Fee inclusion not confirmed.'}" if price else ''),
     growth=show['listener_growth_6m'],growth_artist=(show['growth_artist'] or {}).get('display_name'),growth_detail=(show['growth_artist'] or {}).get('growth_detail'),
     just_announced=show.get('just_announced'),sold_out=show.get('sold_out'),on_sale_label=show.get('on_sale_label'),status=item['Status'],listen=item['Listen'],buy=item['Buy'],calendar=google_calendar_link(show,item['Name'],item['Buy'],calendar_id),calendar_label='Add to Family Google Calendar' if calendar_id else 'Add to Google Calendar',listener_artist=(show['audience_artist'] or {}).get('display_name'),
     sources=[dict(label=x['source_name'],url=x['source_url']) for x in show['sources']],
     photo_source=(show['audience_artist'] or next(iter(show['headliners']),{})).get('image_source'),
     genre_source=next((h.get('genre_source') for h in ([show['audience_artist']] if show['audience_artist'] and show['audience_artist'].get('genre') else show['headliners']) if h.get('genre')),None),
     match_reason=(show['audience_artist'] or next(iter(show['headliners']),{})).get('match_reason','Unresolved; link opens a name search.')))


st.markdown("""<style>
.st-key-client_filter_bar [data-testid=stHorizontalBlock]{gap:12px;align-items:flex-end}
.st-key-client_filter_bar [data-testid=stColumn]:first-child{flex:1 1 800px!important;min-width:0!important;width:auto!important}
.st-key-client_filter_bar [data-testid=stColumn]:last-child{flex:0 0 176px!important;min-width:0!important;width:176px!important}
[data-stale=true]:has(iframe[title*=filter_controls]),[data-stale=true]:has(iframe[title*=concert_table]){opacity:1!important}
@media(max-width:700px){.st-key-client_filter_bar [data-testid=stHorizontalBlock]{flex-wrap:wrap}.st-key-client_filter_bar [data-testid=stColumn]:last-child{margin-left:auto!important}}
</style>""",unsafe_allow_html=True)
core_ids={'brevard-music-center','asheville-music-hall','one-stop','eulogy','hellbender','grey-eagle','orange-peel','harrahs-arena','thomas-wolfe','sierra-nevada'}
core_names=sorted({s['venue_name'] for s in shows if s['venue_id'] in core_ids})
with st.container(key='client_filter_bar'):
 filter_column,email_column=st.columns([8,1.2],gap='small',vertical_alignment='bottom')
with filter_column:
 controls=components.declare_component('filter_controls_v2',path=str(Path(__file__).parent/'filter_controls'))
 filter_change=controls(rows=rows,preferences=st.session_state['live_filter_preferences'],owner=owner,revision=st.session_state['live_filter_revision'],venues=venues,genres=genres,types=show_types,core_venues=core_names,limits=limits,key='filter_controls_'+owner,default=None)
if filter_change and filter_change.get('owner')==owner and isinstance(filter_change.get('revision'),int) and filter_change['revision']>st.session_state['live_filter_revision']:
 st.session_state['live_filter_preferences']=normalize(filter_change.get('preferences'),venues,genres,show_types,upper,limits['growth'])
 st.session_state['live_filter_revision']=filter_change['revision']
current_preferences=st.session_state['live_filter_preferences']
view=current_preferences['review_view']
# Filtering happens immediately in the browser; this rerun only saves the latest choice.
if account_id and current_preferences!=st.session_state.get('filter_preferences_saved'):
 try:
  status_store.save_filters(account_id,current_preferences)
  st.session_state['filter_preferences_saved']=current_preferences
 except Exception:st.warning('Your filters changed, but could not be saved. Try again shortly.')
st.session_state['filter_preferences']=current_preferences
if not account_id and st.session_state.get('guest_filters_loaded'):
 preferences_bridge(preferences=current_preferences,key='guest_preferences_save',default=None)
with email_column,st.container(key='weekly_email_control'):
 email_preferences(account_id,auth_configured)
status_error=st.session_state.pop('status_save_error',None)
if status_error:st.error(status_error)

action=table(rows=rows,key='concert_table_'+(account_id or 'guest'),default=None,account_id=account_id,decisions=st.session_state.get('account_statuses',{}) if account_id else None,review_view=view,filters=current_preferences,filter_revision=st.session_state.get('live_filter_revision',0),limits=limits,acknowledged=st.session_state.get('status_acknowledged',[]))
if action and action.get('event_id')!=st.session_state.get('last_status_event'):
 if action.get('login_requested') and not account_id:
  st.session_state['last_status_event']=action['event_id']
  request_login()
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
with st.expander('Excluded events'):
 from concert_discovery.discovery import excluded_events
 exclusions=excluded_events()
 st.caption('Upcoming stored listings hidden by catalog rules, independent of your filters. Includes duplicates, cancellations and disappeared listings. Events rejected before import are not recorded here.')
 if exclusions:st.dataframe(exclusions,hide_index=True,width='stretch',column_config={'Source':st.column_config.LinkColumn('Source')})
 else:st.caption('No stored upcoming exclusions.')

if account_id:
 from concert_discovery.activity import admin_view
 admin_view(st,activity_store,dict(st.user),st.secrets.get('calendar_defaults',{}).get('owner_email'))
 from concert_discovery.pricing_health import admin_view as pricing_admin_view
 pricing_admin_view(st,dict(st.user),st.secrets.get('calendar_defaults',{}).get('owner_email'),shows)
 from concert_discovery.metadata_outcomes import admin_view as metadata_admin_view
 metadata_admin_view(st,dict(st.user),st.secrets.get('calendar_defaults',{}).get('owner_email'))

if not account_id and auth_configured and not st.session_state.get('login_intro_seen'):
 st.session_state['login_intro_seen']=True
 request_login(arrival=True)

if st.session_state.pop('email_login_requested',False) and not account_id:
 request_login()

from concert_discovery.activity import is_owner
if st.query_params.get('preview_signin') in ('1','welcome') and is_owner(dict(st.user),st.secrets.get('calendar_defaults',{}).get('owner_email')):
 request_login(arrival=st.query_params.get('preview_signin')=='welcome')

if st.session_state.get('login_prompt_requested') and (not account_id or st.query_params.get('preview_signin')):
 login_prompt(arrival=st.session_state['login_prompt_requested']=='arrival')
