import unittest
from datetime import date,datetime,timezone
from unittest.mock import Mock
from concert_discovery.playlist import select_artists,collect_tracks,publish
from concert_discovery.spotify_public import top_track
class PlaylistTests(unittest.TestCase):
 def artist(self,i):return {'spotify_artist_id':str(i).zfill(22),'monthly_listeners':10000-i,'listener_growth_6m':i}
 def test_selection(self):
  artists=[self.artist(i) for i in range(120)]
  shows=[{'show_id':1,'performance_start':date.today().isoformat(),'headliners':artists+artists},{'show_id':2,'performance_start':date.today().isoformat(),'headliners':[dict(self.artist(999),monthly_listeners=999999)]}]
  chosen=select_artists(shows,{1:'live_music',2:'comedy'})
  self.assertEqual(len(chosen),75);self.assertEqual(chosen[:60],artists[:60]);self.assertEqual(chosen[60],artists[119])
 def test_top_track(self):
  sid='a'*22;uri='spotify:track:'+'b'*22
  payload={'entities':{'items':{'spotify:artist:'+sid:{'discography':{'topTracks':{'items':[{'track':{'uri':uri,'name':'Song','artists':{'items':[{'uri':'spotify:artist:'+sid}]}}}]}}}}}}
  self.assertEqual(top_track(payload,sid)['uri'],uri);self.assertIsNone(top_track(payload,'c'*22))
 def test_cache_and_failure(self):
  a=self.artist(1);cache={};fetch=Mock(return_value={'top_track':{'uri':'spotify:track:'+'b'*22,'artist_id':a['spotify_artist_id'],'name':'Song'}})
  now=datetime.now(timezone.utc);self.assertEqual(len(collect_tracks([a],cache,fetch,now)),1)
  collect_tracks([a],cache,fetch,now);fetch.assert_called_once()
  with self.assertRaises(RuntimeError):collect_tracks([self.artist(2)],{},lambda sid:{})
 def test_protect_playlist(self):
  session=Mock()
  with self.assertRaises(RuntimeError):publish([],'token',session)
  session.get.side_effect=[Mock(status_code=200,json=lambda:{'id':'me'}),Mock(status_code=200,json=lambda:{'owner':{'id':'other'}})]
  with self.assertRaises(RuntimeError):publish(['spotify:track:'+str(i).zfill(22) for i in range(50)],'token',session)
  session.put.assert_not_called()
