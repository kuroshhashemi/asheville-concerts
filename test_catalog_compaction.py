import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concert_discovery.source_links import schema, PageReader, encode_markup, decode_markup
from concert_discovery.compact_catalog import compact


class CompactionTests(unittest.TestCase):
    def test_migration_preserves_cached_html_and_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'catalog.sqlite3'
            markup = '<html>Music 🎵</html>' * 100000
            with sqlite3.connect(db) as c:
                schema(c)
                c.execute('CREATE TABLE evidence(value TEXT)')
                c.execute("INSERT INTO evidence VALUES('keep me')")
                c.execute("INSERT INTO identity_page_cache VALUES(?,?,200,datetime('now'))", ('https://example.com/show', markup))
                c.execute("INSERT INTO identity_page_cache VALUES(?,?,200,datetime('now','-40 days'))", ('https://example.com/expired', markup))
            before, after = compact(db)
            self.assertLess(after, before / 10)
            with patch('concert_discovery.source_links.requests.get') as request:
                reader = PageReader(db, budget=0)
                self.assertEqual(reader.get('https://example.com/show'), markup)
                request.assert_not_called()
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute('SELECT value FROM evidence').fetchone()[0], 'keep me')
                self.assertEqual(c.execute('SELECT count(*) FROM identity_page_cache').fetchone()[0], 1)

    def test_plaintext_and_unicode_roundtrip(self):
        markup = 'Spotify artist 🎵 é'
        self.assertEqual(decode_markup(markup), markup)
        self.assertEqual(decode_markup(encode_markup(markup)), markup)


if __name__ == '__main__':
    unittest.main()
