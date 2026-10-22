import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from concert_discovery.pricing_health import report,admin_view
from concert_discovery.storage import connect

class PricingHealthTests(unittest.TestCase):
 def test_owner_guard_prevents_data_loading_for_guests_and_other_users(self):
  with patch('concert_discovery.pricing_health.report') as read:
   for identity in ({},{'email':'friend@example.com','email_verified':True},{'email':'owner@example.com','email_verified':False}):
    st=Mock();admin_view(st,identity,'owner@example.com',[]);st.expander.assert_not_called()
   read.assert_not_called()
 def test_separate_resolved_states_and_categorize_missing_attempts(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=Path(tmp)/'test.sqlite3'
   with connect(db) as c:
    c.execute('CREATE TABLE ticket_price_checks(url_key TEXT,url TEXT,checked_at TEXT,status TEXT,http_status INTEGER,detail TEXT)')
    c.execute("INSERT INTO ticket_price_checks VALUES('etix.com/ticket/p/1','https://www.etix.com/ticket/p/1','2026-10-17T12:00:00Z','blocked',403,'challenge')")
   def show(i,**kw):return dict(show_id=i,title='Example',performance_start='2026-12-01T20:00:00',venue_name='Venue',ticket_url=f'https://www.etix.com/ticket/p/{i}',sources=[],**kw)
   shows=[show(1),show(2,sold_out={'status':'sold_out'}),show(3),show(4,on_sale_label='On Sale 11/1',on_sale_at='2026-11-01'),show(5)]
   prices={'etix.com/ticket/p/3':{'min':0,'max':0},'etix.com/ticket/p/5':{'min':50,'max':100,'resale_only':True}}
   counts,rows=report(shows,prices,db)
   self.assertEqual(counts,{'Missing price':1,'Sold Out':1,'Price / Free':1,'Not yet on sale':1,'Resale':1})
   self.assertEqual([r['Reason'] for r in rows],['Access blocked','Not on sale yet'])
   self.assertIn('Oct 18',rows[0]['Retry eligible (ET)'])
