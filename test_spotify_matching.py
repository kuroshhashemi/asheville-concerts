import unittest
from concert_discovery.spotify_matching import select_candidate
class MatchingTests(unittest.TestCase):
 def test_does_not_choose_first_fuzzy_result(self):
  self.assertIsNone(select_candidate('Luna',[{'id':'a','name':'Luna Sea'}]))
 def test_rejects_ambiguous_exact_names(self):
  self.assertIsNone(select_candidate('Luna',[{'id':'a','name':'Luna'},{'id':'b','name':'Luna'}]))
 def test_handles_punctuation_without_assuming_popularity(self):
  self.assertEqual(select_candidate('Black Country, New Road',[{'id':'b','name':'Black Country New Road'}])['id'],'b')

class ArtworkTests(unittest.TestCase):
 def test_listener_data_survives_missing_artwork(self):
  from unittest.mock import Mock,patch
  from concert_discovery.spotify_public import fetch_public_artist_metrics
  sid='a'*22
  response=Mock(status_code=200,text='stub')
  payload={'entities':{'items':{'spotify:artist:'+sid:{'profile':{'name':'Example'},'stats':{'followers':4,'monthlyListeners':80},'visuals':{'avatarImage':None}}}}}
  with patch('concert_discovery.spotify_public.requests.get',return_value=response),patch('concert_discovery.spotify_public._decode_state',return_value=payload):
   result=fetch_public_artist_metrics(sid,'Example')
  self.assertEqual(result['monthly_listeners'],80)
  self.assertIsNone(result['image_url'])

class BillingTests(unittest.TestCase):
 def test_explicit_bill_keeps_separate_artists(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual([a['name'] for a in parse_performers('Free Throw & Microwave')],['Free Throw','Microwave'])
 def test_does_not_split_a_band_name(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual([a['name'] for a in parse_performers('Caitlin Krisko & The Broadcast')],['Caitlin Krisko & The Broadcast'])

class PrefixTests(unittest.TestCase):
 def test_promoter_and_rescheduled_labels_are_not_artists(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual(parse_performers('RESCHEDULED: Daniel Tosh: My First Farewell Tour')[0]['name'],'Daniel Tosh')
  self.assertEqual(parse_performers('Live Nation Presents: Hudson Westbrook – The Hits Me Tour')[0]['name'],'Hudson Westbrook')
 def test_evening_with_is_not_an_opener_marker(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual([a['name'] for a in parse_performers('An Evening with Kelli O’Hara and the Asheville Symphony')],['Kelli O’Hara','Asheville Symphony'])

class SourceLinkTests(unittest.TestCase):
 def test_rejects_differently_named_source_artist(self):
  from unittest.mock import Mock,patch
  from concert_discovery.spotify_matching import match_bandsintown_link
  response=Mock(status_code=200);response.json.return_value={'name':'Different Artist','links':[]}
  with patch('concert_discovery.spotify_matching.requests.get',return_value=response),patch('concert_discovery.spotify_public.fetch_public_artist_metrics') as fetch:
   self.assertIsNone(match_bandsintown_link({'display_name':'Expected Artist'},None))
   fetch.assert_not_called()

class TourSubtitleTests(unittest.TestCase):
 def test_plus_sign_inside_tour_subtitle_does_not_create_fake_opener(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual([a['name'] for a in parse_performers('GENITORTURERS "LIVE + LEWD TOUR"')],['GENITORTURERS'])
 def test_removes_tour_subtitle(self):
  from concert_discovery.event_sources import parse_performers
  self.assertEqual(parse_performers('Great Lake Swimmers - Caught Light Tour 2026')[0]['name'],'Great Lake Swimmers')

class ListenerValueTests(unittest.TestCase):
 def profile(self,value):
  return {'entities':{'items':{'spotify:artist:'+'a'*22:{'profile':{'name':'Example'},'stats':{'followers':None,'monthlyListeners':value},'visuals':{}}}}}
 def test_explicit_zero_is_valid_even_without_followers(self):
  from unittest.mock import Mock,patch
  from concert_discovery.spotify_public import fetch_public_artist_metrics
  with patch('concert_discovery.spotify_public.requests.get',return_value=Mock(status_code=200,text='stub')),patch('concert_discovery.spotify_public._decode_state',return_value=self.profile(0)):
   self.assertEqual(fetch_public_artist_metrics('a'*22,'Example')['monthly_listeners'],0)
 def test_missing_is_not_converted_to_zero(self):
  from unittest.mock import Mock,patch
  from concert_discovery.spotify_public import fetch_public_artist_metrics,fetch_public_artist_profile
  with patch('concert_discovery.spotify_public.requests.get',return_value=Mock(status_code=200,text='stub')),patch('concert_discovery.spotify_public._decode_state',return_value=self.profile(None)):
   self.assertIsNone(fetch_public_artist_profile('a'*22,'Example')['monthly_listeners'])
   with self.assertRaises(ValueError):fetch_public_artist_metrics('a'*22,'Example')

class EvidenceTests(unittest.TestCase):
 def test_spotify_url_formats(self):
  from concert_discovery.source_links import spotify_artist_ids
  sid='a'*22
  for value in ['spotify:artist:'+sid,'https://open.spotify.com/intl-de/artist/'+sid,'https://open.spotify.com/embed/artist/'+sid]:
   self.assertEqual(spotify_artist_ids(value),{sid})
 def test_multi_artist_page_does_not_assign_unlabeled_links(self):
  from concert_discovery.source_links import page_candidates
  markup='<a href="https://open.spotify.com/artist/'+('a'*22)+'">Listen</a>'
  ids,_=page_candidates(markup,['One','Two'],'https://venue.example/event/one')
  self.assertEqual(ids,{'One':set(),'Two':set()})
 def test_structured_artist_links_keep_their_identity(self):
  from concert_discovery.source_links import page_candidates
  markup='<script type="application/ld+json">{"@type":"MusicEvent","performer":[{"@type":"MusicGroup","name":"One","sameAs":"spotify:artist:'+('a'*22)+'"},{"@type":"MusicGroup","name":"Two","sameAs":"spotify:artist:'+('b'*22)+'"}]}</script>'
  ids,_=page_candidates(markup,['One','Two'],'https://venue.example/event/one')
  self.assertEqual(ids,{'One':{'a'*22},'Two':{'b'*22}})
 def test_conflicting_evidence_is_preserved(self):
  import sqlite3
  from concert_discovery.source_links import record
  c=sqlite3.connect(':memory:')
  record(c,'one','a'*22,'https://one.example','explicit')
  record(c,'one','b'*22,'https://two.example','explicit')
  self.assertEqual(c.execute('SELECT COUNT(*) FROM spotify_source_candidates').fetchone()[0],2)

class CityFeedTests(unittest.TestCase):
 def test_grouped_feed_preserves_artist_ids_and_cursor(self):
  from concert_discovery.spotify_concert_feed import parse_feed
  payload={'data':{'liveEventsFeed':{'sections':[{'paginationKey':'next','concerts':[{'data':{'uri':'spotify:concert:show','title':'One','startDateIsoString':'2099-10-04T20:00-04:00','location':{'name':'The Orange Peel'},'artists':{'items':[{'data':{'uri':'spotify:artist:'+'a'*22,'profile':{'name':'One'}}}]}}}]}]}}}
  rows,cursor=parse_feed(payload)
  self.assertEqual(cursor,'next');self.assertEqual(rows[0]['artist_spotify_links'],{'One':'a'*22})
