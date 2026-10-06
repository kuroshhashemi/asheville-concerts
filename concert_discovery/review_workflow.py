"""Personal review views; keep stored status values compatible with existing accounts."""
STATUS_BY_DECISION={None:'Unread','passed':'Pass','interested':'Interested','going':'Going'}
def statuses_for(view,saved_view='All saved',hide_hidden=True):
    if view=='To Review':return ['Unread','Interested','Going']
    if view=='All':return ['Unread','Pass','Interested','Going']
    if view=='To review':return ['Unread']
    if view=='Hidden':return ['Pass']
    if view=='Saved':return [saved_view] if saved_view in ('Interested','Going') else ['Interested','Going']
    return ['Unread','Interested','Going']+([] if hide_hidden else ['Pass'])
def select_view(shows,view,saved_view='All saved',hide_hidden=True):
    allowed=set(statuses_for(view,saved_view,hide_hidden))
    return [s for s in shows if STATUS_BY_DECISION.get(s.get('decision'),'Unread') in allowed]
