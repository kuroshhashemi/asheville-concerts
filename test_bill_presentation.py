import unittest
from concert_discovery.bill_presentation import performers
class BillingTests(unittest.TestCase):
 def test_unmatched_combo_does_not_repeat_complete_bill(self):
  rows=[{'display_name':'Gillian Welch','spotify_artist_id':'a'},{'display_name':'Gillian Welch & David Rawlings','spotify_artist_id':None},{'display_name':'David Rawlings','spotify_artist_id':'b'}]
  self.assertEqual([x['display_name'] for x in performers(rows,'')],['Gillian Welch','David Rawlings'])
 def test_confirmed_band_is_never_split(self):
  rows=[{'display_name':'Earth & Fire','spotify_artist_id':'a'},{'display_name':'Earth','spotify_artist_id':'b'},{'display_name':'Fire','spotify_artist_id':'c'}]
  self.assertEqual(len(performers(rows,'')),3)
 def test_incomplete_bill_preserves_combo(self):
  rows=[{'display_name':'A & B','spotify_artist_id':None},{'display_name':'A','spotify_artist_id':'a'}]
  self.assertEqual(len(performers(rows,'')),2)

class SpellingTests(unittest.TestCase):
 def test_search_only_variant_not_second_performer(self):
  rows=[{'display_name':'Noah Gundersen','spotify_artist_id':'a'}, {'display_name':'Noah Gunderson','spotify_artist_id':'b','match_status':'candidate','match_reason':'Unique exact normalized name in official Spotify search'}]
  self.assertEqual(len(performers(rows,'Noah Gundersen: Rites of Spring US TOUR FALL 2026')),1)
 def test_both_explicitly_billed_are_preserved(self):
  rows=[{'display_name':'Noah Gundersen','spotify_artist_id':'a'}, {'display_name':'Noah Gunderson','spotify_artist_id':'b','match_status':'candidate','match_reason':'Unique exact normalized name in official Spotify search'}]
  self.assertEqual(len(performers(rows,'Noah Gundersen & Noah Gunderson')),2)
