"""Small account control and public unsubscribe confirmation."""
import streamlit as st
from concert_discovery.email_store import EmailStore


def store():
    settings = st.secrets['supabase']
    return EmailStore(settings['url'], settings['secret'])


def unsubscribe_page():
    token = st.query_params.get('unsubscribe')
    if not token:
        return
    st.title('Asheville Soundcheck')
    st.subheader('Stop weekly emails?')
    st.write('Your saved shows and filters will stay as they are.')
    if st.session_state.get('unsubscribed_token') == token:
        st.success('You’re unsubscribed from weekly emails.')
    elif st.button('Unsubscribe', type='primary'):
        try:
            if store().unsubscribe(token):
                st.session_state['unsubscribed_token'] = token
                st.session_state.pop('email_subscription', None)
                st.success('You’re unsubscribed from weekly emails.')
            else:
                st.warning('This unsubscribe link is no longer valid. You can turn emails off after signing in.')
        except Exception:
            st.error('Could not update your email preference. Please try again.')
    st.link_button('Back to Soundcheck', 'https://asheville-soundcheck.streamlit.app/')
    st.stop()


def preferences(account_id, auth_configured):
    email = st.user.get('email') if account_id else None
    owner = (account_id, email)
    if account_id and st.session_state.get('email_owner') != owner:
        try:
            subscription = store().get(email)
            st.session_state['email_subscription'] = subscription
            st.session_state['email_owner'] = owner
            st.session_state['weekly_email_enabled'] = bool(subscription and subscription['enabled'])
        except Exception:
            st.session_state.pop('email_subscription', None)
    unavailable = bool(account_id and 'email_subscription' not in st.session_state)
    enabled = bool(account_id and st.session_state.get('weekly_email_enabled', False))
    from pathlib import Path
    import streamlit.components.v1 as components
    control=components.declare_component('email_control_v1',path=str(Path(__file__).parent/'email_control'))
    action=control(enabled=enabled,account_id=account_id,unavailable=unavailable,ack=st.session_state.get('email_action_ack'),key='email_control_'+(account_id or 'guest'),default=None)
    if action and action.get('event_id')!=st.session_state.get('email_action_ack'):
        if action.get('login_requested'):
            st.session_state['email_action_ack']=action['event_id']
            st.session_state['email_login_requested']=True
        elif account_id and email and st.user.get('email_verified') is not False:
            try:
                target=bool(action['enabled'])
                st.session_state['email_subscription']=store().set_enabled(email,target,account_id)
                st.session_state['weekly_email_enabled']=target
                st.session_state.pop('email_save_error',None)
            except Exception:
                st.session_state['email_save_error']='Could not save your email preference. Please try again.'
            st.session_state['email_action_ack']=action['event_id']
            st.rerun()
    if st.session_state.get('email_save_error'):st.error(st.session_state['email_save_error'])
