"""Show table, cached artist data, and durable personal statuses."""
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import pandas as pd
import streamlit as st
from concert_discovery.storage import initialize
from concert_discovery.discovery import get_shows,filter_table,compact_audience,decide

st.set_page_config(page_title='Worth a listen · Asheville',page_icon='🎵',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>.block-container{max-width:1600px;padding-top:2rem}h1{letter-spacing:-1px}</style>''',unsafe_allow_html=True)
st.title('Worth a listen')
st.caption('Upcoming Asheville shows')
initialize()
shows=get_shows(user_id='browser-view')
for show in shows:
 choice=st.session_state.get('personal_statuses',{}).get(str(show['show_id']),'Unread')
 show['decision']={'Unread':None,'Pass':'passed','Interested':'interested'}.get(choice)
cols=st.columns([2,1,2])
venues=sorted({s['venue_name'] for s in shows})
selected_venues=cols[0].multiselect('Venues',venues,default=venues,key='table_venues')
minimum=cols[1].selectbox('Monthly listeners',[0,100000,250000,500000,1000000],index=2,format_func=lambda n:'No minimum' if n==0 else compact_audience(n)+'+',key='table_minimum')
statuses=cols[2].multiselect('Status',['Unread','Pass','Interested'],default=['Unread','Interested'],key='table_statuses')
growth_cols=st.columns([1,2,2])
use_growth=growth_cols[0].checkbox('Filter by growth',value=False)
minimum_growth=growth_cols[1].number_input('Minimum six-month growth (%)',value=0.0,step=5.0,disabled=not use_growth,help='Independent of monthly listeners. Shows without six-month history are excluded when this filter is on.')
selected=filter_table(shows,selected_venues,statuses,minimum,minimum_growth if use_growth else None)
st.caption(f'{len(selected)} shows · Use the Status dropdown to save your choice.')
labels={None:'Unread','passed':'Pass','interested':'Interested'}
data=[]
for s in selected:
 a=s['audience_artist']
 headliners=s['headliners']
 name=' & '.join(dict.fromkeys(h['display_name'] for h in headliners)) if headliners else s['title']
 genre=(a.get('genre') if a else None) or next((h.get('genre') for h in headliners if h.get('genre')),None)
 listen=a['spotify_profile_url'] if a else next((h['spotify_profile_url'] for h in headliners if h['spotify_profile_url']),None)
 image=(a.get('image_url') if a else None) or next((h.get('image_url') for h in headliners if h.get('image_url')),None)
 data.append({'show_id':s['show_id'],'Date':datetime.fromisoformat(s['performance_start']).date(),'Artist image':image,'Name':name,
              'Venue icon':s.get('venue_icon'),'Venue':s['venue_name'],'Genre':genre.title() if genre else '—','Monthly listeners':compact_audience(s['audience']),
              '6-month growth':s['listener_growth_6m'],'Status':labels.get(s['decision'],'Unread'),'Listen':listen or 'https://open.spotify.com/search/'+quote(name),
              'Buy':s['ticket_url'] or s['official_event_url'] or s['venue_calendar_url']})
if data:
 import streamlit.components.v1 as components
 table=components.declare_component('concert_table',path=str(Path(__file__).parent/'show_table'))
 rows=[]
 for item,show in zip(data,selected):
  rows.append(dict(id=item['show_id'],date=item['Date'].strftime('%a %b %d'),name=item['Name'],artist_image=item['Artist image'],
      venue=item['Venue'],venue_icon=item['Venue icon'],genre=item['Genre'],listeners=show['audience'],listeners_label=item['Monthly listeners'],
      status=item['Status'],listen=item['Listen'],buy=item['Buy']))
 action=table(rows=rows,key='concert_table',default=None)
 if action and action.get('event_id')!=st.session_state.get('last_status_event'):
  choices=action.get('decisions',{})
  if isinstance(choices,dict):
   st.session_state['personal_statuses']={str(k):v for k,v in choices.items() if v in ('Unread','Pass','Interested')}
   st.session_state['last_status_event']=action['event_id']
   st.rerun()
else:
 st.info('No shows match these filters. Select more venues or statuses, or choose No minimum.')
st.caption('Six-month growth: — means not enough history. No minimum includes shows without audience data. Growth and audience filters work independently.')
with st.expander('Data notes'):
 st.write('Genre labels come from available event sources and earlier verified artist records. Artist mappings are source-backed candidates unless manually confirmed. Audience uses the largest measured headliner on each bill; an unknown co-headliner may have a larger audience.')
 st.write('Official calendars cover Music Hall, One Stop, Grey Eagle, Orange Peel, Hellbender, Harrah’s arena, and Thomas Wolfe Auditorium. Eulogy uses its linked DICE calendar. Sierra Nevada uses public Songkick listings for Mills River. Coverage can still be incomplete; statuses save in this browser.')
 st.write('Statuses currently save in this browser and survive app restarts. Cross-device status syncing will come with account login.')

