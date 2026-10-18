import unittest
from unittest.mock import patch
from concert_discovery.digest_preflight import prepare
class PreflightTests(unittest.TestCase):
 def test_selected_rows_only_and_bounded_calls(self):
  shows=[{'dedupe_key':'one','headliners':[{'artist_id':'a','spotify_artist_id':'spotify-a'}]}]
  targets=['concert_discovery.matching_queue.run','concert_discovery.refresh.enrich','concert_discovery.pastspot.refresh_history','concert_discovery.price_refresh.refresh','concert_discovery.ticketmaster_prices.refresh','concert_discovery.metadata_outcomes.synchronize','concert_discovery.operations_alerts.check']
  from contextlib import ExitStack
  with ExitStack() as stack:
   mocks=[stack.enter_context(patch(t,return_value={})) for t in targets]
   stack.enter_context(patch('concert_discovery.discovery.get_shows',return_value=shows+[{'dedupe_key':'other'}]))
   prepare(shows,'db')
   self.assertEqual(mocks[0].call_args.kwargs['artist_ids'],{'a'})
   self.assertEqual(mocks[0].call_args.kwargs['limit'],5)
   self.assertEqual(mocks[1].call_args.kwargs['limit'],10)
   self.assertEqual(mocks[2].call_args.kwargs['spotify_ids'],{'spotify-a'})
   self.assertEqual(mocks[3].call_args.kwargs['shows'],shows)
   self.assertEqual(mocks[4].call_args.kwargs['limit'],2)
