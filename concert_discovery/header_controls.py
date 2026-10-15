"""Compact header actions and signed-in request dialog."""
import base64
import json
from urllib.parse import urlparse
import time
import streamlit as st
from concert_discovery.api_sources import secret
from concert_discovery.feature_requests import submit

PLAYLIST_URL='https://open.spotify.com/playlist/7u3M8wAdhF71129WF72miQ'
SPOTIFY='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#102c43" d="M12 0a12 12 0 1 0 0 24 12 12 0 0 0 0-24Zm5.5 17.3c-.2.4-.7.5-1 .3-2.8-1.7-6.2-2.1-10.2-1.2-.4.1-.8-.2-.9-.6-.1-.4.2-.8.6-.9 4.4-1 8.3-.6 11.3 1.3.4.2.5.7.2 1.1Zm1.5-3.4c-.3.4-.8.6-1.2.3-3.2-2-8.1-2.6-11.9-1.5-.5.1-1-.2-1.1-.7-.1-.4.2-.9.7-1.1 4.3-1.3 9.7-.6 13.3 1.6.5.3.6.9.2 1.4Zm.1-3.7C15.3 8 9 7.8 5.4 8.9c-.6.2-1.2-.1-1.4-.7-.2-.6.1-1.2.7-1.4 4.2-1.3 11.2-1.1 15.5 1.5.5.3.7 1 .4 1.5-.3.5-1 .7-1.5.4Z"/></svg>'


def dismiss_request():
    st.session_state.pop('request_dialog_open',None)

def request_dialog():
    @st.dialog('Request a feature',on_dismiss=dismiss_request)
    def show():
        st.write('What would make Soundcheck better for you?')
        if st.session_state.get('request_submitted'):
            st.success('Submitted')
            st.caption('Thanks for helping shape Soundcheck.')
            return
        with st.form('feature_request_form'):
            text=st.text_area('Your request',max_chars=4000,height=140,placeholder='I’d love to…')
            send=st.form_submit_button('Submit',type='primary',width='stretch')
        if send:
            if time.time()-st.session_state.get('request_last_sent',0)<60:
                st.info('Please wait a minute before sending another request.')
                return
            try:
                settings=st.secrets.get('feature_requests',{})
                submit(dict(st.user),text,settings.get('EMAIL_SENDER') or secret('EMAIL_SENDER'),settings.get('EMAIL_APP_PASSWORD') or secret('EMAIL_APP_PASSWORD'))
            except ValueError as error:
                st.warning(str(error))
            except Exception:
                st.error('We couldn’t confirm delivery. Please try again later.')
            else:
                st.session_state['request_last_sent']=time.time()
                st.session_state['request_submitted']=True
                st.rerun()
    show()


def render(auth_configured,request_login):
    logged_in=bool(auth_configured and st.user.is_logged_in)
    spotify='data:image/svg+xml;base64,'+base64.b64encode(SPOTIFY.encode()).decode()
    st.markdown('''<style>
[data-testid=stElementContainer]:has(>[data-testid=stMarkdown]>[data-testid=stMarkdownContainer]>style:only-child){display:none!important}.st-key-brand_header{gap:0!important}.st-key-client_filter_bar{padding-top:12px!important}.soundcheck-header{margin-bottom:0!important}.st-key-header_requests button>span{margin:0!important;width:18px!important;display:flex;align-items:center;justify-content:center}.st-key-banner_auth{top:2.8rem!important}.st-key-banner_auth [data-testid=stHorizontalBlock]{gap:8px;align-items:center;flex-wrap:nowrap}.st-key-banner_auth [data-testid=stColumn]{flex:0 0 auto!important;width:auto!important;min-width:0!important;align-self:flex-start!important}.st-key-banner_auth [data-testid=stColumn]>[data-testid=stVerticalBlock]{gap:0!important}.st-key-banner_auth [data-testid=stColumn]>[data-testid=stVerticalBlock]>[data-testid=stLayoutWrapper]:has(.st-key-avatar_logout_handler){display:none!important}.st-key-banner_auth button,.st-key-banner_auth a[data-testid=stBaseLinkButton-secondary]{height:42px;min-height:42px;border-radius:999px!important;background:#102c43!important;color:white!important;border:0!important;white-space:nowrap;padding:0 14px!important}.st-key-banner_auth p{font:600 13px system-ui!important;line-height:1.25!important}.st-key-banner_auth button,.st-key-banner_auth a{font:600 13px system-ui!important;gap:8px!important;align-items:center!important;justify-content:center!important;box-shadow:none!important}.st-key-banner_auth button [data-testid=stIconMaterial]{font-size:18px!important;width:18px;height:18px;line-height:18px}.st-key-banner_google_signin button{background:#247e79!important}.st-key-banner_auth .st-key-playlist_header a[data-testid],.st-key-banner_auth .st-key-header_requests button{background:#bde6de!important;color:#102c43!important}.st-key-banner_google_signin button::before,.st-key-google_signin_popup button::before{content:'';width:18px;height:18px;flex-shrink:0;background:currentColor;mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36z M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.05.96-3.38.96-2.6 0-4.8-1.75-5.59-4.1H3.07v2.59A10 10 0 0 0 12 22z M6.41 13.94a6 6 0 0 1 0-3.88V7.47H3.07a10 10 0 0 0 0 9.06l3.34-2.59z M12 5.96c1.47 0 2.79.5 3.82 1.49l2.86-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.93 5.47l3.34 2.59A6 6 0 0 1 12 5.96z'/%3E%3C/svg%3E") center/contain no-repeat}.st-key-avatar_trigger button,.soundcheck-avatar-photo{border:0!important;box-shadow:none!important}.st-key-avatar_logout_handler{display:none!important}.soundcheck-account-menu{position:fixed;z-index:1000001;box-sizing:border-box;background:white;box-shadow:0 8px 24px #102c4330;border:0;font:600 13px system-ui}.soundcheck-account-menu [role=menuitem]{gap:8px!important}.soundcheck-account-menu [role=menuitem]::before{content:'';width:18px;height:18px;flex:0 0 18px;background:currentColor;mask-position:center;mask-size:contain;mask-repeat:no-repeat}.soundcheck-menu-spotify::before{mask-image:url("'''+spotify+'''")}.soundcheck-menu-request::before{mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-5 3V6a2 2 0 0 1 2-2Z'/%3E%3C/svg%3E")}.soundcheck-menu-signout::before{mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M14 8l4 4-4 4M8 12h12'/%3E%3C/svg%3E")}.soundcheck-account-menu a{display:flex;align-items:center;min-height:38px;padding:0 12px;color:#102c43;text-decoration:none;border-radius:10px}.soundcheck-account-menu a:hover{background:#eef7f5}.soundcheck-account-menu button{display:flex;align-items:center;min-height:38px;padding:0 12px;cursor:pointer}.soundcheck-account-menu[hidden]{display:none!important}.st-key-avatar_trigger button svg{display:none!important}.st-key-avatar_trigger button{position:relative;overflow:hidden;background:#bde6de!important;box-shadow:inset 0 0 0 4px #bde6de!important}.soundcheck-avatar-photo{position:absolute;inset:4px;width:calc(100% - 8px);height:calc(100% - 8px);object-fit:cover;border-radius:50%;pointer-events:none}.soundcheck-account-menu{padding:4px!important;min-width:144px!important;width:144px!important;border-radius:14px!important}.soundcheck-account-menu [data-testid=stVerticalBlock]{gap:0!important}.soundcheck-account-menu button{border:0!important;background:transparent!important;color:#102c43!important;font:600 13px system-ui!important;width:100%!important;border-radius:10px!important;justify-content:flex-start!important}.soundcheck-account-menu button:hover{background:#eef7f5!important}.st-key-header_behavior{height:0!important;margin:0!important;display:none!important}.st-key-playlist_header a::before{content:'';width:18px;height:18px;background:url("'''+spotify+'''") center/contain no-repeat;margin-right:0;flex-shrink:0}.st-key-avatar_trigger button{width:42px!important;padding:0!important;border-radius:50%!important;background:#bde6de!important;color:#102c43!important}.st-key-avatar_trigger button [data-testid=stIconMaterial]{display:none}.st-key-avatar_trigger button p{font-size:14px!important}.st-key-banner_auth button:hover,.st-key-banner_auth a:hover{border-color:#bde6de!important;filter:brightness(1.15)}
.soundcheck-mobile-menu-item{display:none!important}
@media(max-width:700px){.st-key-banner_auth{top:32px!important;bottom:auto!important;right:0!important}.soundcheck-header{padding:24px 1rem!important}.soundcheck-header h1{max-width:calc(100vw - 172px)!important}.st-key-banner_auth [data-testid=stColumn]:has(.st-key-playlist_header),.st-key-banner_auth [data-testid=stColumn]:has(.st-key-header_requests){display:none!important}.soundcheck-mobile-menu-item{display:flex!important}.soundcheck-account-menu{width:200px!important;min-width:200px!important}}
@media(max-width:420px){.st-key-banner_auth button,.st-key-banner_auth a[data-testid=stBaseLinkButton-secondary]{padding:0 10px!important}.st-key-banner_auth [data-testid=stHorizontalBlock]{gap:5px}}
</style>''',unsafe_allow_html=True)
    with st.container(key='banner_auth'):
        playlist,requests,account=st.columns([2.2,1.4,.6],gap='small',vertical_alignment='top')
        with playlist,st.container(key='playlist_header'):
            st.link_button('Concerts Playlist',PLAYLIST_URL)
        with requests:
            if st.button('Requests',icon=':material/chat_bubble_outline:',key='header_requests'):
                if logged_in:
                    st.session_state['request_submitted']=False
                    st.session_state['request_dialog_open']=True
                else:request_login()
        with account:
            if logged_in:
                name=st.user.get('name') or st.user.get('email') or 'You'
                initials=''.join(part[0] for part in name.split()[:2]).upper()
                st.button(initials,key='avatar_trigger')
                with st.container(key='avatar_logout_handler'):
                    st.button('Sign out',on_click=st.logout,key='avatar_signout')
            elif auth_configured:
                st.button('Sign In',on_click=request_login,key='banner_google_signin')
    header_behavior(st.user.get('picture','') if logged_in else '')
    if st.session_state.get('request_dialog_open') and logged_in:
        request_dialog()


def header_behavior(picture):
    """Below-button tooltips and a photo layered over fallback initials."""
    import streamlit.components.v1 as components
    parsed=urlparse(picture or '')
    photo=picture if parsed.scheme=='https' and (parsed.hostname or '').endswith('.googleusercontent.com') else ''
    with st.container(key='header_behavior'):
        components.html('<script>'+HEADER_SCRIPT.replace('__PHOTO__',json.dumps(photo).replace('<','\\u003c'))+'</script>',height=0)


HEADER_SCRIPT=r"""
const doc=parent.document,photo=__PHOTO__;
let closeTimer=null;
function positionHeader(){
 const banner=doc.querySelector('.st-key-banner_auth'),logo=doc.querySelector('.soundcheck-header img'),brand=doc.querySelector('.st-key-brand_header');
 if(!banner||!logo||!brand)return;
 const r=logo.getBoundingClientRect();banner.style.setProperty('top',(r.top+r.height/2-brand.getBoundingClientRect().top-21)+'px','important');
}
if(parent.soundcheckHeaderPosition)parent.removeEventListener('resize',parent.soundcheckHeaderPosition);
parent.soundcheckHeaderPosition=positionHeader;parent.addEventListener('resize',positionHeader);
function decorate(){
 positionHeader();
 const badge=doc.querySelector('.st-key-avatar_trigger button');
 if(!badge)return;
 badge.setAttribute('aria-label','Your account');badge.setAttribute('aria-haspopup','menu');badge.setAttribute('aria-controls','soundcheck-account-menu');
 let image=badge.querySelector('.soundcheck-avatar-photo');
 if(photo&&badge.dataset.failedPhoto!==photo&&(!image||image.dataset.source!==photo)){
  if(image)image.remove();image=doc.createElement('img');image.className='soundcheck-avatar-photo';image.alt='';image.hidden=true;image.dataset.source=photo;
  image.onload=()=>{image.hidden=false};image.onerror=()=>{badge.dataset.failedPhoto=photo;image.remove()};image.src=photo;badge.append(image);
 }else if(!photo&&image)image.remove();
 let menu=doc.getElementById('soundcheck-account-menu');
 if(!menu){
  menu=doc.createElement('div');menu.id='soundcheck-account-menu';menu.className='soundcheck-account-menu';menu.setAttribute('role','menu');menu.setAttribute('aria-label','Your account');menu.hidden=true;
  const playlist=doc.createElement('a');playlist.className='soundcheck-mobile-menu-item';playlist.setAttribute('role','menuitem');playlist.textContent='AVL Concerts Playlist';playlist.classList.add('soundcheck-menu-spotify');playlist.href='https://open.spotify.com/playlist/7u3M8wAdhF71129WF72miQ';playlist.target='_blank';playlist.rel='noopener';playlist.onclick=()=>closeMenu();menu.append(playlist);
  const request=doc.createElement('button');request.className='soundcheck-mobile-menu-item';request.type='button';request.setAttribute('role','menuitem');request.textContent='Request a Feature';request.classList.add('soundcheck-menu-request');request.onclick=()=>{closeMenu();doc.querySelector('.st-key-header_requests button')?.click()};menu.append(request);
  const item=doc.createElement('button');item.type='button';item.setAttribute('role','menuitem');item.textContent='Sign out';item.classList.add('soundcheck-menu-signout');
  item.onclick=()=>{closeMenu();doc.querySelector('.st-key-avatar_signout button')?.click()};menu.append(item);doc.body.append(menu);
 }
 const closeMenu=()=>{menu.hidden=true;badge.setAttribute('aria-expanded','false')};
 const openMenu=()=>{clearTimeout(closeTimer);const r=badge.getBoundingClientRect();menu.style.top=(r.bottom+8)+'px';menu.hidden=false;menu.style.left=Math.max(12,r.right-menu.offsetWidth)+'px';badge.setAttribute('aria-expanded','true')};
 const scheduleClose=()=>{clearTimeout(closeTimer);closeTimer=setTimeout(closeMenu,160)};
 badge.onmouseenter=openMenu;badge.onmouseleave=scheduleClose;menu.onmouseenter=()=>clearTimeout(closeTimer);menu.onmouseleave=scheduleClose;
 if(!badge.dataset.menuBound){
  badge.dataset.menuBound='true';
  badge.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();openMenu()},true);
  badge.addEventListener('keydown',e=>{if(['Enter',' ','ArrowDown'].includes(e.key)){e.preventDefault();e.stopImmediatePropagation();openMenu();Array.from(menu.querySelectorAll('[role=menuitem]')).find(el=>el.getClientRects().length)?.focus()}if(e.key==='Escape')closeMenu()},true);
  menu.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenu();badge.focus()}if(e.key==='Tab')closeMenu()});
  doc.addEventListener('pointerdown',e=>{if(!badge.contains(e.target)&&!menu.contains(e.target))closeMenu()});
 }
 badge.setAttribute('aria-expanded',String(!menu.hidden));
}
decorate();
if(parent.soundcheckHeaderObserver)parent.soundcheckHeaderObserver.disconnect();
parent.soundcheckHeaderObserver=new MutationObserver(decorate);parent.soundcheckHeaderObserver.observe(doc.body,{childList:true,subtree:true});
if(!parent.soundcheckHeaderTooltips){
 parent.soundcheckHeaderTooltips=true;
 const tips=[['.st-key-playlist_header a','Playlist that automatically updates based on upcoming concert artists'],['.st-key-header_requests button','Request a feature']];
 let tip=null;
 const hide=()=>{if(tip)tip.remove();tip=null};
 const show=target=>{
  const match=tips.find(([selector])=>target.closest(selector));if(!match)return;
  hide();const button=target.closest(match[0]),rect=button.getBoundingClientRect();
  tip=doc.createElement('div');tip.setAttribute('role','tooltip');tip.textContent=match[1];
  tip.style.cssText='position:fixed;z-index:1000002;box-sizing:border-box;max-width:260px;width:max-content;background:#fff;color:#102c43;padding:14px 16px;border-radius:16px;box-shadow:0 8px 24px #102c4330;font:600 13px system-ui;line-height:1.45;pointer-events:none';
  doc.body.append(tip);tip.style.top=(rect.bottom+9)+'px';tip.style.left=Math.max(12,Math.min(rect.right-tip.offsetWidth,doc.documentElement.clientWidth-tip.offsetWidth-12))+'px';
 };
 doc.addEventListener('mouseover',e=>show(e.target));doc.addEventListener('focusin',e=>show(e.target));
 doc.addEventListener('mouseout',e=>{if(tips.some(([s])=>e.target.closest(s))&&!e.target.closest('button,a')?.contains(e.relatedTarget))hide()});
 doc.addEventListener('focusout',hide);doc.addEventListener('click',hide);doc.addEventListener('scroll',hide,true);
}
"""
