"""Connect private server-side tracking to Streamlit's existing Google login."""
import logging
from pathlib import Path
from uuid import uuid4
from concert_discovery.login_health import LoginStore,attempt_key
LOG=logging.getLogger(__name__)

def setup(st):
    import streamlit.components.v1 as components
    try:
        config=st.secrets.get('supabase',{})
        store=LoginStore(config['url'],config['secret']) if config.get('url') and config.get('secret') else None
    except (KeyError,FileNotFoundError):store=None
    if store and st.user.is_logged_in and 'login_health_first_sign_in' not in st.session_state:
        try:
            from concert_discovery.accounts import user_key
            prior=store.call('GET','app_user_activity',params={'user_id':'eq.'+user_key(dict(st.user)),'select':'user_id','limit':1})
            st.session_state['login_health_first_sign_in']=not bool(prior)
        except Exception:LOG.warning('First-sign-in classification unavailable.')
    bridge=components.declare_component('login_health_bridge_v1',path=str(Path(__file__).parent/'auth_bridge'))
    value=bridge(logged_in=bool(st.user.is_logged_in),ack=st.session_state.get('login_health_ack'),key='login_health_bridge',default={}) or {}
    if attempt_key(value.get('prepared')):st.session_state['login_health_prepared']=value['prepared']
    returned=attempt_key(value.get('returned'))
    if store and st.user.is_logged_in and returned and st.session_state.get('login_health_ack')!=returned:
        try:
            store.finish(returned,dict(st.user),first_sign_in=st.session_state.get('login_health_first_sign_in'))
            st.session_state['login_health_ack']=returned
        except Exception:LOG.warning('Login success tracking could not be saved; no identity or provider response logged.')
    return store

def start(st,store):
    attempt=st.session_state.get('login_health_prepared') or str(uuid4())
    try:
        if store:store.start(attempt)
    except Exception:LOG.warning('Login start tracking could not be saved.')
    try:st.login()
    except Exception:
        try:
            if store:store.finish(attempt,error=True)
        except Exception:LOG.warning('Login error tracking could not be saved.')
        st.error('Sign-in could not start. Please try again shortly.')
