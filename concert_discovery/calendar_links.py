"""Google Calendar event drafts; never writes events automatically."""
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

def google_calendar_link(show,title,ticket_url,calendar_id=None):
    start=datetime.fromisoformat(show['performance_start'])
    zone=show.get('timezone') or 'America/New_York'
    details='Tickets / show details: '+ticket_url
    if len(show['performance_start'])<=10 or (start.hour==0 and start.minute==0):
        dates=start.strftime('%Y%m%d')+'/'+(start+timedelta(days=1)).strftime('%Y%m%d')
        details+='\nShow time unavailable; confirm the venue schedule.'
    else:
        if start.tzinfo is None:start=start.replace(tzinfo=ZoneInfo(zone))
        end=start.astimezone(timezone.utc)+timedelta(hours=3)
        dates=start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'/'+end.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    params={'action':'TEMPLATE','text':title,'dates':dates,'ctz':zone,'location':show['venue_name'],'details':details}
    if calendar_id:params['src']=calendar_id
    return 'https://calendar.google.com/calendar/render?'+urlencode(params)
