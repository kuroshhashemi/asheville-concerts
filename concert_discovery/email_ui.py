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
    with st.popover('Emails', icon=':material/mail_outline:'):
        st.write('**Weekly new shows**')
        st.write('All newly discovered shows, with Spotify Listeners, Trending, prices, and links.')
        st.caption('Mondays · Your filters don’t affect emails.')
        if not account_id:
            if auth_configured:
                st.button('Sign in to subscribe', on_click=st.login, key='email_sign_in')
            else:
                st.caption('Sign-in is required to subscribe.')
            return
        email = st.user.get('email')
        if not email or st.user.get('email_verified') is False:
            st.warning('A verified Google email address is required.')
            return
        owner = (account_id, email)
        if st.session_state.get('email_owner') != owner or 'email_subscription' not in st.session_state:
            try:
                subscription = store().get(email)
            except Exception:
                st.error('Email preferences are unavailable. Please reload to try again.')
                return
            st.session_state['email_owner'] = owner
            st.session_state['email_subscription'] = subscription
            st.session_state['weekly_email_enabled'] = bool(subscription and subscription['enabled'])

        def save():
            previous = st.session_state['email_subscription']
            try:
                st.session_state['email_subscription'] = store().set_enabled(email, st.session_state['weekly_email_enabled'], account_id)
                st.session_state.pop('email_save_error', None)
            except Exception:
                st.session_state['weekly_email_enabled'] = bool(previous and previous['enabled'])
                st.session_state['email_save_error'] = 'Could not save your preference. Please try again.'

        st.toggle('Email me new shows', key='weekly_email_enabled', on_change=save)
        st.caption('Delivered to ' + email)
        if st.session_state.get('email_save_error'):
            st.error(st.session_state['email_save_error'])
