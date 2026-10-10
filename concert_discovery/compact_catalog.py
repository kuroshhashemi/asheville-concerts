"""Compact disposable HTML caches before publishing, preserving catalog evidence."""
import sqlite3
from pathlib import Path
from concert_discovery.storage import DATABASE_PATH
from concert_discovery.source_links import encode_markup


def compact(db_path=DATABASE_PATH):
    path = Path(db_path)
    before = path.stat().st_size
    with sqlite3.connect(path) as connection:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='identity_page_cache'").fetchone()
        if exists:
            # These pages are already expired for matching after seven days.
            # Keep a month for debugging; durable identity evidence lives elsewhere.
            connection.execute("DELETE FROM identity_page_cache WHERE checked_at < datetime('now','-30 days')")
            for url, markup in connection.execute("SELECT url,markup FROM identity_page_cache").fetchall():
                if markup and not markup.startswith('zlib64:'):
                    connection.execute("UPDATE identity_page_cache SET markup=? WHERE url=?", (encode_markup(markup), url))
        connection.commit()
        connection.execute('VACUUM')
    after = path.stat().st_size
    print(f'Catalog compacted: {before:,} -> {after:,} bytes')
    if after >= 95_000_000:
        raise RuntimeError('Catalog remains too large to publish safely; preserve the previous published catalog.')
    return before, after


if __name__ == '__main__':
    compact()
