import unittest
from datetime import date
from concert_discovery.prices import structured,advertised,from_markup,from_ticket_markup
from concert_discovery.sierra_calendar import parse_api
class PriceCollectionTests(unittest.TestCase):
 def test_fee_inclusive_provider_beats_calendar_base_price(self):
  from concert_discovery.prices import for_show,url_key
  show={'official_event_url':'https://venue.org/show','ticket_url':'https://tickets.org/show'}
  prices={url_key(show['official_event_url']):{'min':50,'max':50},url_key(show['ticket_url']):{'min':31.39,'max':31.39,'includes_fees':True}}
  self.assertEqual(for_show(show,prices)['min'],31.39)
 def test_eventbrite_price_region_ignores_other_event_prices(self):
  html='<div>$5</div><section aria-label="Tickets price and event schedule">From $31.39</section>'
  self.assertTrue(from_ticket_markup('https://www.eventbrite.com/e/show',html)['includes_fees'])
  self.assertEqual(from_ticket_markup('https://www.eventbrite.com/e/show',html)['min'],31.39)
 def test_provider_totals_ignore_description_and_upsells(self):
  etix='<p>VIP merchandise $500</p><div role="combobox" aria-label="GA, Price: $14.31"></div><div role="combobox" aria-label="GA, Price: $14.31"></div>'
  self.assertEqual(from_ticket_markup('https://www.etix.com/ticket/p/1',etix)['min'],14.31)
  tixr='<div class="ticket" data-row-type="primary" data-product-state="OPEN"><div class="info">General Admission $32.57 ($25 + $7.57 fees)</div></div><div class="ticket" data-row-type="secondary" data-product-state="OPEN"><div class="info">Parking $5</div></div><div class="ticket" data-row-type="primary" data-product-state="CLOSED"><div class="info">Early bird $10</div></div>'
  self.assertEqual(from_ticket_markup('https://www.tixr.com/groups/a/events/a-1',tixr)['min'],32.57)
  self.assertIsNone(from_ticket_markup('https://www.etix.com/ticket/p/1','<p>Artist raised $1000 for charity</p>'))
 def test_brevard_uses_adult_legend_not_student_seat_range(self):
  markup='<div id="tn-syos-legend-container"><li>Adult : $62.98</li><li>Student : $35.23</li></div><div aria-label="M12, $35.23 to $62.98"></div>'
  self.assertEqual(from_ticket_markup('https://secured.brevardmusic.org/1947/1954',markup)['min'],62.98)
  self.assertEqual(from_ticket_markup('https://secured.brevardmusic.org/1947/1954',markup.replace('Adult :','Adult'))['min'],62.98)
 def test_free_jambase_is_scoped_to_current_event(self):
  self.assertEqual(from_ticket_markup('https://www.jambase.com/show/band','<h1>Band FREE SHOW</h1>')['min'],0)
  self.assertIsNone(from_ticket_markup('https://www.jambase.com/show/band','<h1>Band</h1><h2>Nearby FREE SHOW</h2>'))
 def test_sierra_free_label_belongs_to_one_event_card(self):
  from unittest.mock import patch
  from concert_discovery.prices import save_sierra_card_prices
  markup='<div class="event-card"><a href="/event/band">Band</a><p class="free-tag">THIS IS A FREE EVENT!</p></div><div class="event-card"><a href="/event/paid">Paid Band</a></div>'
  with patch('concert_discovery.prices.save') as saved:
   self.assertEqual(save_sierra_card_prices(markup),1)
   self.assertEqual(saved.call_args[0][0]['source_url'],'https://sierranevada.com/event/band')
 def test_usd_only(self):
  self.assertEqual(structured({'priceRanges':[{'currency':'USD','min':25,'max':40}]})['min'],25)
  self.assertIsNone(structured({'offers':[{'price':10,'priceCurrency':'EUR'}]}))
  self.assertIsNone(advertised('No price listed'))
  self.assertEqual(advertised('THIS IS A FREE EVENT!')['min'],0)
 def test_event_json_only(self):
  self.assertEqual(from_markup('<script type="application/ld+json">{"@type":"MusicEvent","offers":{"price":"30","priceCurrency":"USD"}}</script>')['min'],30)
  self.assertIsNone(from_markup('<script type="application/ld+json">{"@type":"Product","offers":{"price":5,"priceCurrency":"USD"}}</script>'))
  self.assertIsNone(from_markup('<script type="application/ld+json">{"@type":"MusicEvent","offers":{"price":0,"priceCurrency":"USD"}}</script>'))
  self.assertEqual(from_markup('<script type="application/ld+json">{"@type":"MusicEvent","isAccessibleForFree":true,"offers":{"price":0,"priceCurrency":"USD"}}</script>')['min'],0)
 def test_nested_etix_offers_and_ranges(self):
  markup='<script type="application/ld+json">{"mainEntity":{"@type":"MusicEvent","offers":{"@type":"AggregateOffer","offers":[{"name":"Adult","price":20,"priceCurrency":"USD"},{"name":"Student","price":10,"priceCurrency":"USD"}]}}}</script>'
  self.assertEqual(from_markup(markup)['min'],20)
  self.assertEqual(from_ticket_markup('https://www.etix.com/ticket/p/1','<div role="combobox" aria-label="Adult, Price: From $23.25 to $34.45"></div>')['max'],34.45)
 def test_see_tickets_ignores_upsell_events(self):
  markup='<div id="eventview"><li><span id="subtotal_1">$42.59</span><select id="tt_1"></select></li><div id="addtomyorderbox1"><li><span id="subtotal_2">$5</span><select id="tt_2"></select></li></div></div>'
  self.assertEqual(from_ticket_markup('https://wl.eventim.us/event/band/123456',markup)['min'],42.59)
 def test_harrah_ignores_related_event_cards(self):
  markup='<p>KNOW BEFORE YOU GO $12 per person. Free for children under 12</p><div class="event-subtitle">$5 at the Door</div>'
  self.assertEqual(from_ticket_markup('https://www.harrahscherokeecenterasheville.com/events/current/',markup)['min'],12)
 def test_sierra_city_and_identity(self):
  base={'title':'Band &#038; Friends','url':'https://sierranevada.com/event/a','start_date':'2026-10-20 19:00:00','description':'THIS IS A FREE EVENT!'}
  rows=parse_api({'events':[{**base,'venue':{'city':'Chico'}},{**base,'venue':{'city':'Mills River'}}]},today=date(2026,10,13))
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['title'],'Band & Friends');self.assertEqual(rows[0]['advertised_price']['min'],0)

 def test_ticketmaster_resale_requires_single_ticket_evidence(self):
  markup='<p>Prices include fees (before taxes).</p><ul role="menu" aria-label="Ticket listings sorted by lowest price"><li><button>Select Verified Resale Ticket $158.70</button></li></ul>'
  url='https://www.ticketmaster.com/event/2D00648FDC34CEFB'
  self.assertIsNone(from_ticket_markup(url,markup))
  price=from_ticket_markup(url,markup,selected_quantity=1)
  self.assertEqual(price['min'],158.70);self.assertTrue(price['resale_only'])
  mixed=markup.replace('</ul>','<li><button>Select Standard Admission $175.00</button></li></ul>')
  self.assertFalse(from_ticket_markup(url,mixed,selected_quantity=1)['resale_only'])
 def test_etix_single_ticket_excludes_bundle_discount(self):
  h='<div role="combobox" aria-label="ADVANCED, Price: $45.85"></div><div role="combobox" aria-label="$60 Two Pack, Price: $30.00"></div>'
  self.assertEqual(from_ticket_markup('https://www.etix.com/ticket/p/1',h)['min'],45.85)

 def test_day_specific_free_admission_not_copied_to_paid_day(self):
  body='<p>DATE Sunday, December 6, 2026</p><p>AVAILABILITY Saturday is $10 | Sunday is free to the public.</p>'
  url='https://www.harrahscherokeecenterasheville.com/events/example/'
  self.assertEqual(from_ticket_markup(url,body)['min'],0)
  self.assertIsNone(from_ticket_markup(url,body.replace('DATE Sunday','DATE Saturday')))
