"""Shared concert data storage; user-specific tables are reserved for later."""

from datetime import date, datetime, timezone
from pathlib import Path
import re
import gzip
import threading
import sqlite3
import unicodedata
from typing import Dict, List, Optional
from urllib.parse import quote


PROJECT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_DIR / "concert_data.sqlite3"

VENUE_ROWS = [
    ("pulp", "Pulp", "https://theorangepeel.net/what-is-pulp/", "Pulp", "Separate room operated by The Orange Peel."),
    ('one-stop','The One Stop','https://ashevillemusichall.com/','The One Stop','Separate room from Asheville Music Hall.'),
    ('harrahs-arena',"Harrah’s Cherokee Center · Arena",'https://www.harrahscherokeecenterasheville.com/events-tickets/','ExploreAsheville.com Arena','Arena within Harrah’s Cherokee Center.'),
    ('thomas-wolfe','Thomas Wolfe Auditorium','https://www.harrahscherokeecenterasheville.com/events-tickets/','Thomas Wolfe Auditorium','Auditorium within Harrah’s Cherokee Center.'),
    ('sierra-nevada','Sierra Nevada · Mills River','https://sierranevada.com/events/mills-river','Sierra Nevada','Mills River only; includes amphitheater and High Gravity room.'),
    ("asheville-music-hall", "Asheville Music Hall", "https://ashevillemusichall.com/", "Asheville Music Hall", "The public feed sometimes lists The One Stop separately; verify the event room."),
    ("eulogy", "Eulogy", "https://burialbeer.com/pages/eulogy", "Eulogy", "The official page has a DICE-powered calendar with more shows than the city-feed sample."),
    ("hellbender", "Hellbender", "https://hellbenderavl.com/", "Hellbender", "Promoted by The Orange Peel; Orange Peel pages cross-list Hellbender shows. Use the actual event venue and dedupe by ticket/show identity."),
    ("grey-eagle", "The Grey Eagle", "https://www.thegreyeagle.com/", "Grey Eagle", "The feed includes both the hall and patio; keep the reported room for review."),
    ("orange-peel", "The Orange Peel", "https://theorangepeel.net/", "Orange Peel", "The promoter page may include Hellbender; do not infer actual venue from promoter."),
]

from concert_discovery.additional_venues import ADDITIONAL_VENUES
VENUE_ROWS.extend((vid, name, url, alias, "JamBase coverage; official calendar completeness not yet audited.") for vid, name, url, alias in ADDITIONAL_VENUES)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS venues (
    venue_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    official_url TEXT NOT NULL,
    feed_alias TEXT NOT NULL,
    coverage_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS shows (
    show_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    venue_calendar_url TEXT NOT NULL,
    venue_id TEXT NOT NULL REFERENCES venues(venue_id),
    title TEXT NOT NULL,
    performance_start TEXT NOT NULL,
    timezone TEXT,
    official_event_url TEXT,
    ticket_url TEXT,
    date_status TEXT NOT NULL,
    date_note TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS show_sources (
    source_key TEXT PRIMARY KEY,
    show_id INTEGER NOT NULL REFERENCES shows(show_id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    venue_as_reported TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artists (
    artist_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    spotify_artist_id TEXT UNIQUE,
    spotify_profile_url TEXT,
    match_status TEXT NOT NULL DEFAULT 'unresolved',
    match_confidence REAL,
    match_reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS show_artists (
    show_id INTEGER NOT NULL REFERENCES shows(show_id) ON DELETE CASCADE,
    artist_id TEXT NOT NULL REFERENCES artists(artist_id),
    billing_role TEXT NOT NULL,
    role_confidence REAL NOT NULL,
    role_source TEXT NOT NULL,
    role_note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (show_id, artist_id)
);

CREATE TABLE IF NOT EXISTS artist_metric_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id TEXT NOT NULL REFERENCES artists(artist_id),
    provider TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    followers INTEGER,
    monthly_listeners INTEGER,
    popularity INTEGER,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_saved INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS venue_source_coverage (
    run_id INTEGER NOT NULL REFERENCES collection_runs(run_id) ON DELETE CASCADE,
    venue_id TEXT NOT NULL REFERENCES venues(venue_id),
    feed_events_found INTEGER NOT NULL DEFAULT 0,
    sample_shows_saved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, venue_id)
);

-- Reserved for a later multi-user release. No accounts or decision UI exists now.
CREATE TABLE IF NOT EXISTS user_show_decisions (
    user_id TEXT NOT NULL,
    show_id INTEGER NOT NULL REFERENCES shows(show_id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (decision IN ('interested', 'passed')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, show_id)
);

CREATE TABLE IF NOT EXISTS user_notification_preferences (
    user_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    cadence TEXT NOT NULL DEFAULT 'weekly',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artist_genres (
    artist_id TEXT PRIMARY KEY REFERENCES artists(artist_id), genre TEXT, source_url TEXT
);
CREATE TABLE IF NOT EXISTS artist_images (
    artist_id TEXT PRIMARY KEY REFERENCES artists(artist_id), image_url TEXT,
    source_url TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendar_checks (
    check_id TEXT PRIMARY KEY,venue_id TEXT NOT NULL,source_url TEXT NOT NULL,checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendar_presence (
    show_id INTEGER PRIMARY KEY REFERENCES shows(show_id),misses INTEGER NOT NULL,checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS show_review_exclusions (
    show_id INTEGER PRIMARY KEY REFERENCES shows(show_id), reason TEXT NOT NULL, evidence_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_availability (
    source_key TEXT PRIMARY KEY, show_id INTEGER NOT NULL REFERENCES shows(show_id),
    status TEXT NOT NULL CHECK(status IN ('sold_out','available')),
    source_url TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS venue_icons (
    venue_id TEXT PRIMARY KEY REFERENCES venues(venue_id), icon_url TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_seed_lock = threading.Lock()

def ensure_catalog_seed():
    """Upgrade the pre-history catalog once; preserve later scheduled refreshes."""
    seed = PROJECT_DIR / 'catalog_seed.sqlite3.gz'
    if not seed.exists():return
    with _seed_lock:
        if DATABASE_PATH.exists():
            with sqlite3.connect(str(DATABASE_PATH)) as current:
                if current.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='listener_history'").fetchone():return
        payload = gzip.decompress(seed.read_bytes())
        if not payload.startswith(b'SQLite format 3\x00'):raise ValueError('Invalid packaged catalog')
        temporary = DATABASE_PATH.with_suffix('.seed-tmp')
        temporary.write_bytes(payload)
        temporary.replace(DATABASE_PATH)

def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    if db_path is None:ensure_catalog_seed()
    connection = sqlite3.connect(str(db_path or DATABASE_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(db_path: Optional[Path] = None) -> None:
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        show_cols = [row["name"] for row in connection.execute("PRAGMA table_info(shows)").fetchall()]
        if "official_event_url" not in show_cols:
            connection.execute("ALTER TABLE shows ADD COLUMN official_event_url TEXT")
        connection.executemany(
            "INSERT OR IGNORE INTO venues (venue_id, name, official_url, feed_alias, coverage_note) VALUES (?, ?, ?, ?, ?)",
            VENUE_ROWS,
        )
        from concert_discovery.additional_venues import VENUE_ICONS
        connection.executemany("INSERT OR IGNORE INTO venue_icons(venue_id,icon_url) VALUES (?,?)", VENUE_ICONS.items())


def stable_artist_id(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    return slug or "unknown-artist"


def upsert_show(connection: sqlite3.Connection, event: Dict[str, object]) -> int:
    ticket_url = str(event.get("ticket_url") or "").strip()
    ticket_identity = ticket_url.split("?", 1)[0].rstrip("/").casefold()
    show_date = str(event["performance_start"])[:10]
    if ticket_identity:
        dedupe_key = "ticket:{}:{}:{}".format(event["venue_id"],ticket_identity, str(event["performance_start"]))
    else:
        normalized_title = " ".join(str(event["title"]).casefold().split())
        dedupe_key = "event:{}:{}:{}".format(event["venue_id"], str(event["performance_start"]), normalized_title)
    from concert_discovery.reconciliation import catalog_rows,duplicate,canonical
    priors=catalog_rows(connection,event['venue_id'],show_date)
    incoming=dict(event,sources=[{'source_name':event.get('source_name','')}],headliners=[{'display_name':p['name']} for p in event.get('performers',[]) if 'headliner' in p.get('role','')])
    for prior in priors:
        if duplicate(incoming,prior,priors+[incoming]):
            dedupe_key=prior['dedupe_key'];break
    # Source identities continue to resolve even after a reversible consolidation.
    source_existing=connection.execute('SELECT show_id FROM show_sources WHERE source_key=?',(event['source_key'],)).fetchone()
    if source_existing:
        sid=canonical(connection,source_existing['show_id'])
        dedupe_key=connection.execute('SELECT dedupe_key FROM shows WHERE show_id=?',(sid,)).fetchone()[0]
    existing=connection.execute('SELECT * FROM shows WHERE dedupe_key=?',(dedupe_key,)).fetchone()
    if existing and str(event['title']).casefold()==existing['title'].casefold():
        event=dict(event);event['title']=existing['title']
    if existing and not str(event['performance_start'])[11:] and str(existing['performance_start'])[11:]:
        event=dict(event);event['performance_start']=existing['performance_start']
    if existing and existing['date_status']=='venue_confirmed' and not event.get('source_name','').endswith('Official'):
        event=dict(event)
        for col in ('title','performance_start','official_event_url','ticket_url','date_status','date_note'):
            event[col]=existing[col]
        ticket_url=event.get('ticket_url') or ticket_url
    venue = next(row for row in VENUE_ROWS if row[0] == event["venue_id"])
    connection.execute(
        """INSERT INTO shows
           (dedupe_key, venue_calendar_url, venue_id, title, performance_start,
                        timezone, official_event_url, ticket_url, date_status, date_note, last_seen_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(dedupe_key) DO UPDATE SET
             title=excluded.title,
             performance_start=excluded.performance_start,
             timezone=excluded.timezone,
                         official_event_url=COALESCE(excluded.official_event_url, shows.official_event_url),
             ticket_url=COALESCE(excluded.ticket_url, shows.ticket_url),
             date_status=excluded.date_status,
             date_note=excluded.date_note,
             last_seen_at=excluded.last_seen_at""",
        (
            dedupe_key,
            venue[2],
            event["venue_id"],
            event["title"],
            event["performance_start"],
            event.get("timezone"),
            event.get("official_event_url"),
            ticket_url or None,
            event["date_status"],
            event.get("date_note", ""),
            utc_now(),
        ),
    )
    show_row = connection.execute(
        "SELECT show_id FROM shows WHERE dedupe_key=?", (dedupe_key,)
    ).fetchone()
    show_id = int(show_row["show_id"])
    connection.execute("CREATE TABLE IF NOT EXISTS show_discovery(show_id INTEGER PRIMARY KEY,first_seen_at TEXT,eligible INTEGER)")
    connection.execute("INSERT OR IGNORE INTO show_discovery VALUES(?,?,?)",(show_id,utc_now(),int(existing is None)))
    add_show_source(
        connection,
        show_id,
        str(event["source_key"]),
        str(event["source_name"]),
        str(event["source_event_id"]),
        str(event["source_url"]),
        str(event.get("venue_as_reported", "")),
    )
    if event.get('ticket_availability') in ('sold_out','available'):
        connection.execute('''INSERT INTO ticket_availability VALUES(?,?,?,?,?)
            ON CONFLICT(source_key) DO UPDATE SET show_id=excluded.show_id,status=excluded.status,
            source_url=excluded.source_url,observed_at=excluded.observed_at''',
            (event['source_key'],show_id,event['ticket_availability'],event['source_url'],utc_now()))
    from concert_discovery.event_classification import save as save_classification
    save_classification(connection,show_id,event)
    spotify_links = {
        " ".join(str(label).casefold().split()): spotify_id
        for label, spotify_id in event.get("artist_spotify_links", {}).items()
    }
    if event.get('source_name','').endswith('Official') and event.get('performers'):
        connection.execute('DELETE FROM show_artists WHERE show_id=?',(show_id,))
    for performer in event.get("performers", []):
        name = str(performer["name"]).strip()
        # Preserve a verified existing identity when the source adds/removes "The".
        article_key=lambda n:re.sub(r'^the\s+','',n.strip().casefold())
        aliases=[dict(r) for r in connection.execute('SELECT * FROM artists WHERE spotify_artist_id IS NOT NULL') if article_key(r['display_name'])==article_key(name)]
        if len(aliases)==1:name=aliases[0]['display_name']
        elif not aliases:
            # A cleaner source lineup must not orphan a previously source-verified
            # identity stored under this very bill's tour/project label.
            from concert_discovery.reconciliation import same_bill
            verified_bill=[dict(r) for r in connection.execute("SELECT * FROM artists WHERE spotify_artist_id IS NOT NULL AND match_status IN ('source_link','manual_confirmed')")
                if r['display_name'].strip().casefold()==str(event['title']).strip().casefold() and (same_bill(name,r['display_name']) or r['display_name'].casefold().startswith(name.casefold()+' - '))]
            if len(verified_bill)==1:name=verified_bill[0]['display_name']
        normalized_name = " ".join(name.casefold().split())
        artist_id = upsert_artist(
            connection,
            name,
            spotify_artist_id=spotify_links.get(normalized_name),
        )
        if spotify_links.get(normalized_name):
            from concert_discovery.source_links import record
            record(connection,artist_id,spotify_links[normalized_name],str(event["source_url"]),"Provider explicit Spotify link")
        add_show_artist(
            connection,
            show_id,
            artist_id,
            str(performer["role"]),
            float(performer["confidence"]),
            str(event["source_url"]),
            str(performer.get("note", "")),
        )
    return show_id

def upsert_artist(
    connection: sqlite3.Connection,
    name: str,
    spotify_artist_id: Optional[str] = None,
    match_reason: str = "No source-provided Spotify artist URL; left unmatched for manual review.",
) -> str:
    from concert_discovery.artist_identity import key
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='artist_name_aliases'").fetchone():
        from concert_discovery.spotify_matching import name_key
        alias=connection.execute('SELECT artist_id FROM artist_name_aliases WHERE name_key=?',(name_key(name),)).fetchone()
        if alias:return alias[0]
    variants=[dict(r) for r in connection.execute('SELECT * FROM artists') if key(r['display_name'])==key(name)]
    compatible=[r for r in variants if not spotify_artist_id or not r['spotify_artist_id'] or r['spotify_artist_id']==spotify_artist_id]
    compatible.sort(key=lambda r:(not bool(r['spotify_artist_id']),r['artist_id']))
    artist_id = compatible[0]['artist_id'] if compatible else stable_artist_id(name)
    now = utc_now()
    profile_url = (
        "https://open.spotify.com/artist/" + spotify_artist_id
        if spotify_artist_id
        else None
    )
    if spotify_artist_id:
        owner = connection.execute('SELECT artist_id FROM artists WHERE spotify_artist_id=?', (spotify_artist_id,)).fetchone()
        if owner and owner[0] != artist_id:
            spotify_artist_id = None
            profile_url = None
        elif match_reason.startswith('No source-provided'):
            match_reason = 'Spotify profile linked by an event data source; identity still requires validation.'
    status = "source_link" if spotify_artist_id else "unresolved"
    confidence = None
    connection.execute(
        """INSERT OR IGNORE INTO artists
           (artist_id, display_name, spotify_artist_id, spotify_profile_url,
            match_status, match_confidence, match_reason, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (artist_id, name, spotify_artist_id, profile_url, status, confidence, match_reason, now),
    )
    prior=connection.execute('SELECT display_name FROM artists WHERE artist_id=?',(artist_id,)).fetchone()
    if prior and prior[0].rstrip(' -–:')==name and prior[0]!=name:
        connection.execute('UPDATE artists SET display_name=? WHERE artist_id=?',(name,artist_id))
    if spotify_artist_id:
        conflict=connection.execute('SELECT artist_id FROM artists WHERE spotify_artist_id=?',(spotify_artist_id,)).fetchone()
        if not conflict or conflict[0]==artist_id:
            connection.execute('UPDATE artists SET spotify_artist_id=?,spotify_profile_url=?,match_status=?,match_reason=?,updated_at=? WHERE artist_id=? AND spotify_artist_id IS NULL',
                (spotify_artist_id,profile_url,status,match_reason,now,artist_id))
    return artist_id


def save_manual_spotify_match(artist_id: str, spotify_artist_id: str, db_path: Optional[Path] = None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9]{22}", spotify_artist_id.strip()):
        raise ValueError("Enter the 22-character Spotify artist ID from the artist profile URL.")
    value = spotify_artist_id.strip()
    with connect(db_path) as connection:
        connection.execute(
            """UPDATE artists SET spotify_artist_id = ?, spotify_profile_url = ?,
               match_status = 'manual_confirmed', match_confidence = NULL,
               match_reason = 'Manually confirmed by reviewer.', updated_at = ?
               WHERE artist_id = ?""",
            (value, "https://open.spotify.com/artist/" + value, utc_now(), artist_id),
        )


def confirm_candidate_match(artist_id: str, db_path: Optional[Path] = None) -> None:
    """Durably confirm an existing candidate Spotify match."""
    with connect(db_path) as connection:
        connection.execute(
            """UPDATE artists SET match_status = 'manual_confirmed', match_confidence = NULL,
               match_reason = 'Candidate confirmed by reviewer.', updated_at = ?
               WHERE artist_id = ? AND spotify_artist_id IS NOT NULL""",
            (utc_now(), artist_id),
        )


def clear_artist_spotify_match(artist_id: str, db_path: Optional[Path] = None) -> None:
    """Durably reset an artist's match to unresolved and clear Spotify IDs."""
    with connect(db_path) as connection:
        connection.execute(
            """UPDATE artists SET spotify_artist_id = NULL, spotify_profile_url = NULL,
               match_status = 'unresolved', match_confidence = NULL,
               match_reason = 'Reset to unresolved by reviewer.', updated_at = ?
               WHERE artist_id = ?""",
            (utc_now(), artist_id),
        )


def get_artist_metric_history(artist_id: str, db_path: Optional[Path] = None) -> List[Dict[str, object]]:
    """Retrieve full metric snapshot history for an artist."""
    with connect(db_path) as connection:
        rows = connection.execute(
            """SELECT snapshot_id, retrieved_at, followers, monthly_listeners, popularity, status, detail, source_url
               FROM artist_metric_snapshots
               WHERE artist_id = ?
               ORDER BY snapshot_id DESC""",
            (artist_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_metric_snapshot(
    connection: sqlite3.Connection,
    artist_id: str,
    *,
    followers: Optional[int] = None,
    monthly_listeners: Optional[int] = None,
    popularity: Optional[int] = None,
    status: str,
    detail: str = "",
    source_url: Optional[str] = None,
    provider: str = "spotify_public_page",
) -> None:
    connection.execute(
        """INSERT INTO artist_metric_snapshots
           (artist_id, provider, retrieved_at, followers, monthly_listeners,
            popularity, status, detail, source_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (artist_id, provider, utc_now(), followers, monthly_listeners, popularity, status, detail, source_url),
    )


def add_show_source(
    connection: sqlite3.Connection,
    show_id: int,
    source_key: str,
    source_name: str,
    source_event_id: str,
    source_url: str,
    venue_as_reported: str,
) -> None:
    connection.execute(
        """INSERT INTO show_sources
           (source_key, show_id, source_name, source_event_id, source_url,
            venue_as_reported, observed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_key) DO UPDATE SET
             show_id=excluded.show_id, source_url=excluded.source_url,
             venue_as_reported=excluded.venue_as_reported,
             observed_at=excluded.observed_at""",
        (source_key, show_id, source_name, source_event_id, source_url, venue_as_reported, utc_now()),
    )


def add_show_artist(
    connection: sqlite3.Connection,
    show_id: int,
    artist_id: str,
    role: str,
    confidence: float,
    source: str,
    note: str = "",
) -> None:
    connection.execute(
        """INSERT INTO show_artists
           (show_id, artist_id, billing_role, role_confidence, role_source, role_note)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(show_id, artist_id) DO UPDATE SET
             billing_role=excluded.billing_role,
             role_confidence=excluded.role_confidence,
             role_source=excluded.role_source,
             role_note=excluded.role_note""",
        (show_id, artist_id, role, confidence, source, note),
    )


def get_review_rows(db_path: Optional[Path] = None, limit: Optional[int] = None) -> List[Dict[str, object]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """SELECT a.artist_id, a.display_name, a.spotify_artist_id,
                      a.spotify_profile_url, a.match_status, a.match_confidence,
                      a.match_reason, s.show_id, s.title, s.performance_start, s.timezone,
                      s.venue_id, v.name AS venue_name, s.venue_calendar_url,
                      s.official_event_url,
                      (SELECT source_url FROM show_sources ss WHERE ss.show_id=s.show_id
                       ORDER BY ss.source_name LIMIT 1) AS source_url,
                      s.ticket_url, s.date_status, s.date_note,
                      sa.billing_role, sa.role_confidence, sa.role_note,
                      (SELECT followers FROM artist_metric_snapshots ms
                       WHERE ms.artist_id=a.artist_id AND ms.status='success'
                         AND ((a.spotify_artist_id IS NOT NULL AND ms.source_url = a.spotify_profile_url)
                              OR (a.spotify_artist_id IS NULL AND ms.source_url IS NULL))
                       ORDER BY ms.snapshot_id DESC LIMIT 1) AS followers,
                      (SELECT monthly_listeners FROM artist_metric_snapshots ms
                       WHERE ms.artist_id=a.artist_id AND ms.status='success'
                         AND ((a.spotify_artist_id IS NOT NULL AND ms.source_url = a.spotify_profile_url)
                              OR (a.spotify_artist_id IS NULL AND ms.source_url IS NULL))
                       ORDER BY ms.snapshot_id DESC LIMIT 1) AS monthly_listeners,
                      (SELECT retrieved_at FROM artist_metric_snapshots ms
                       WHERE ms.artist_id=a.artist_id AND ms.status='success'
                         AND ((a.spotify_artist_id IS NOT NULL AND ms.source_url = a.spotify_profile_url)
                              OR (a.spotify_artist_id IS NULL AND ms.source_url IS NULL))
                       ORDER BY ms.snapshot_id DESC LIMIT 1) AS metric_retrieved_at,
                      (SELECT status FROM artist_metric_snapshots ms
                       WHERE ms.artist_id=a.artist_id
                         AND ((a.spotify_artist_id IS NOT NULL AND ms.source_url = a.spotify_profile_url)
                              OR (a.spotify_artist_id IS NULL AND (ms.source_url IS NULL OR ms.status IN ('unresolved', 'unmatched'))))
                       ORDER BY ms.snapshot_id DESC LIMIT 1) AS metric_status,
                      (SELECT detail FROM artist_metric_snapshots ms
                       WHERE ms.artist_id=a.artist_id
                         AND ((a.spotify_artist_id IS NOT NULL AND ms.source_url = a.spotify_profile_url)
                              OR (a.spotify_artist_id IS NULL AND (ms.source_url IS NULL OR ms.status IN ('unresolved', 'unmatched'))))
                       ORDER BY ms.snapshot_id DESC LIMIT 1) AS metric_detail
               FROM show_artists sa
               JOIN artists a ON a.artist_id = sa.artist_id
               JOIN shows s ON s.show_id = sa.show_id
               JOIN venues v ON v.venue_id=s.venue_id
             WHERE substr(s.performance_start, 1, 10) >= ?
               ORDER BY s.performance_start, s.venue_id, a.display_name"""
             , (date.today().isoformat(),)
         ).fetchall()
    artists_map: Dict[str, Dict[str, object]] = {}
    for row in rows:
        aid = str(row["artist_id"])
        show_info = {
            "show_id": row["show_id"],
            "title": row["title"],
            "venue_id": row["venue_id"],
            "venue_name": row["venue_name"],
            "performance_start": row["performance_start"],
            "timezone": row["timezone"],
            "venue_calendar_url": row["venue_calendar_url"],
            "official_event_url": row["official_event_url"],
            "source_url": row["source_url"],
            "ticket_url": row["ticket_url"],
            "date_status": row["date_status"],
            "date_note": row["date_note"],
            "billing_role": row["billing_role"],
            "role_confidence": row["role_confidence"],
            "role_note": row["role_note"],
        }
        if aid not in artists_map:
            item = dict(row)
            # Normalize legacy 'unmatched' to 'unresolved'
            if item.get("match_status") == "unmatched":
                item["match_status"] = "unresolved"
            item["shows"] = [show_info]
            item["spotify_search_url"] = (
                "https://open.spotify.com/search/" + quote(item["display_name"])
                if not item["spotify_artist_id"]
                else item["spotify_profile_url"]
            )
            artists_map[aid] = item
        else:
            artists_map[aid]["shows"].append(show_info)

    review = list(artists_map.values())
    if limit is not None:
        review = review[:limit]
    return review


def get_coverage(db_path: Optional[Path] = None) -> List[Dict[str, object]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """SELECT v.venue_id, v.name, v.official_url, v.coverage_note,
                      COUNT(s.show_id) AS show_count,
                      MIN(s.performance_start) AS first_show,
                      MAX(s.performance_start) AS last_show
                      , COALESCE(c.feed_events_found, 0) AS feed_events_found,
                      COALESCE(c.sample_shows_saved, 0) AS sample_shows_saved
                FROM venues v LEFT JOIN shows s ON s.venue_id = v.venue_id
                  AND substr(s.performance_start, 1, 10) >= ?
                LEFT JOIN venue_source_coverage c ON c.venue_id=v.venue_id AND c.run_id=(
                    SELECT MAX(run_id) FROM collection_runs WHERE status IN ('success','partial')
                )
               GROUP BY v.venue_id ORDER BY v.name"""
             , (date.today().isoformat(),)
         ).fetchall()
    return [dict(row) for row in rows]


def get_artists(db_path: Optional[Path] = None) -> List[Dict[str, object]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """SELECT artist_id, display_name, spotify_artist_id, spotify_profile_url,
                      match_status, match_confidence, match_reason
               FROM artists ORDER BY display_name COLLATE NOCASE"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_run(db_path: Optional[Path] = None) -> Optional[Dict[str, object]]:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM collection_runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
