import json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from concert_discovery.web_publish import publish
class PublishTests(unittest.TestCase):
 def test_pointer_only_after_snapshot_saved(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'catalog.json';p.write_text(json.dumps({'schema':1,'version':'test','updated_at':'2026-11-24','rows':[{}]}))
   with patch.dict(os.environ,{'SUPABASE_URL':'https://example.invalid','SUPABASE_SECRET_KEY':'test'}),patch('concert_discovery.web_publish.requests.post') as post:
    post.return_value.json.return_value=[];publish(p)
    urls=[c.args[0] for c in post.call_args_list];self.assertTrue(urls[0].endswith('/test.json'));self.assertTrue(urls[1].endswith('/latest.json'))
   with patch.dict(os.environ,{'SUPABASE_URL':'https://example.invalid','SUPABASE_SECRET_KEY':'test'}),patch('concert_discovery.web_publish.requests.post') as post:
    post.return_value.raise_for_status.side_effect=RuntimeError('failed upload')
    with self.assertRaises(RuntimeError):publish(p)
    self.assertEqual(post.call_count,1)
 def test_invalid_catalog_never_published(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'catalog.json';p.write_text('{}')
   with patch('concert_discovery.web_publish.requests.post') as post:
    with self.assertRaises(ValueError):publish(p)
    post.assert_not_called()
if __name__=='__main__':unittest.main()
