import tempfile,unittest
from pathlib import Path
from concert_discovery.storage import initialize
from concert_discovery.show_validation import partition
class ValidationTests(unittest.TestCase):
 def row(self,i,time='2027-01-01 20:00:00'):
  return dict(show_id=i,dedupe_key=str(i),title='Artist',venue_id='venue',venue_name='Venue',performance_start=time,sources=[{'source_name':'JamBase'}],headliners=[{'artist_id':'artist','display_name':'Artist'}])
 def test_conflicts_withheld_but_unrelated_row_retained(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'db.sqlite3';initialize(db)
   a,b,valid=self.row(1),self.row(2,'2027-01-02 20:00:00'),self.row(3,'2027-04-01 20:00:00')
   ready,held=partition([a,b,valid],[a,b,valid],db)
   self.assertEqual([s['show_id'] for s in ready],[3])
   self.assertEqual(len(held),2);self.assertIn('date/time',held[0]['reasons'][0])
 def test_invalid_core_fields_withheld(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'db.sqlite3';initialize(db)
   bad=self.row(1,'not-a-date');bad['sources']=[]
   ready,held=partition([bad],[bad],db)
   self.assertEqual(ready,[]);self.assertIn('date',held[0]['reasons'][0]);self.assertIn('source',held[0]['reasons'][0])
