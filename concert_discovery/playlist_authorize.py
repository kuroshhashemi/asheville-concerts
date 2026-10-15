"""One-time loopback OAuth. Never logs codes/tokens; no playlist edits here."""
import os
import secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode,urlparse,parse_qs
import requests
from concert_discovery.api_sources import secret

REDIRECT='http://127.0.0.1:8766/callback'

def main():
    client=secret('SPOTIFY_CLIENT_ID');password=secret('SPOTIFY_CLIENT_SECRET')
    if not client or not password:raise RuntimeError('Existing Spotify app credentials are missing.')
    state=secrets.token_urlsafe(32)
    auth='https://accounts.spotify.com/authorize?'+urlencode({'client_id':client,'response_type':'code','redirect_uri':REDIRECT,'scope':'playlist-modify-public','state':state,'show_dialog':'true'})
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def page(self,text,status=200):
            self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.end_headers()
            self.wfile.write(('<html><body style="font:18px system-ui;max-width:600px;margin:80px auto"><h1>Soundcheck playlist</h1>'+text+'</body></html>').encode())
        def do_GET(self):
            path=urlparse(self.path)
            if path.path=='/':
                self.page('<p>Use the Spotify account that owns the playlist. This allows Soundcheck to manage public playlists; the updater only targets your supplied concert playlist.</p><a href="'+auth+'">Authorize with Spotify</a>');return
            query=parse_qs(path.query)
            if path.path!='/callback' or not secrets.compare_digest(query.get('state',[''])[0],state):self.page('Invalid authorization response.',400);return
            if self.server.completed:self.page('Authorization already saved. You can close this tab.');return
            if not query.get('code'):self.page('Authorization cancelled. Return to the setup page to try again.',400);return
            try:
                r=requests.post('https://accounts.spotify.com/api/token',auth=(client,password),data={'grant_type':'authorization_code','code':query['code'][0],'redirect_uri':REDIRECT},timeout=20)
                if r.status_code!=200:raise RuntimeError()
                result=r.json();token=result.get('refresh_token')
                if not token or 'playlist-modify-public' not in result.get('scope','').split():raise RuntimeError()
                # Verify the consenting account owns exactly the configured playlist before saving.
                from concert_discovery.playlist import PLAYLIST_ID
                headers={'Authorization':'Bearer '+result['access_token']}
                me=requests.get('https://api.spotify.com/v1/me',headers=headers,timeout=20)
                playlist=requests.get('https://api.spotify.com/v1/playlists/'+PLAYLIST_ID,headers=headers,timeout=20)
                if me.status_code!=200 or playlist.status_code!=200 or me.json().get('id')!=playlist.json().get('owner',{}).get('id'):
                    self.page('This account could not be verified as the playlist owner. Please start again with the account that created the playlist.',400);return
                target=Path(__file__).resolve().parents[2]/'work/research/spotify.env'
                lines=[l for l in target.read_text().splitlines() if not l.startswith('SPOTIFY_REFRESH_TOKEN=')]
                tmp=target.with_suffix('.tmp');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                with os.fdopen(fd,'w') as output:output.write('\n'.join(lines)+'\nSPOTIFY_REFRESH_TOKEN='+token+'\n')
                tmp.replace(target);target.chmod(0o600)
                self.server.completed=True
                self.page('<p>Authorization saved securely. No playlist changes have been made yet. You can close this tab and return to Codex.</p>')
            except Exception:self.page('Authorization could not be saved. No playlist changes were made. Return to the setup page to retry.',500)
    server=ThreadingHTTPServer(('127.0.0.1',8766),Handler);server.completed=False;server.timeout=600
    print('Open http://127.0.0.1:8766/ after registering '+REDIRECT+' in Spotify app settings.',flush=True)
    while not server.completed:server.handle_request()
    server.server_close()
if __name__=='__main__':main()
