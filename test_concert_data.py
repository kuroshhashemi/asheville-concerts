import tempfile
import unittest
from pathlib import Path
from datetime import date,timedelta

from concert_discovery.event_sources import (
    VENUES,
    check_date,
    parse_performers,
    select_validation_sample,
    venue_id_for,
)
from concert_discovery.storage import (
    add_metric_snapshot,
    add_show_source,
    connect,
    get_coverage,
    get_review_rows,
    initialize,
    upsert_artist,
    upsert_show,
    utc_now,
)


class ConcertDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "concert-test.sqlite3"
        initialize(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_performer_roles_are_parsed_from_explicit_billing(self):
        performers = parse_performers("The Midnight: Time Machines w/ Bonnie McKee")
        self.assertEqual([person["name"] for person in performers], ["The Midnight", "Bonnie McKee"])
        self.assertEqual([person["role"] for person in performers], ["headliner", "support"])

    def test_date_conflict_is_flagged(self):
        status, note = check_date("Coming Friday October 9 | Flocktoberfest", "2026-10-01 20:00:00")
        self.assertEqual(status, "date_conflict")
        self.assertIn("different", note)

    def test_hellbender_is_not_misclassified_as_orange_peel(self):
        self.assertEqual(venue_id_for("Hellbender"), "hellbender")
        self.assertEqual(venue_id_for("Hellbender by The Orange Peel"), "hellbender")

    def test_cross_listed_ticket_dedupes_show_but_keeps_both_sources(self):
        base = {
            "ticket_url": "https://tickets.example/show/123?utm_source=feed",
            "venue_id": "hellbender",
            "title": "Dylan Gossett & Charles Wesley Godwin",
            "performance_start": "2026-10-02T18:30:00",
            "timezone": "America/New_York",
            "date_status": "venue_confirmed",
            "date_note": "Confirmed at Hellbender.",
            "performers": [{"name": "Dylan Gossett", "role": "co-headliner", "confidence": 1.0, "note": "Official title."}],
            "artist_spotify_links": {},
        }
        with connect(self.db_path) as connection:
            ids = []
            for source_key, source_name, venue_reported in (
                ("source-a", "Official venue", "Hellbender"),
                ("source-b", "Promoter listing", "Hellbender by The Orange Peel"),
            ):
                event = dict(base, source_key=source_key, source_name=source_name, source_event_id=source_key, source_url="https://example.com/" + source_key, venue_as_reported=venue_reported)
                ids.append(upsert_show(connection, event))

        self.assertEqual(ids[0], ids[1])
        with connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM shows").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM show_sources").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM artists").fetchone()[0], 1)

    def test_failed_refresh_does_not_hide_last_successful_metrics(self):
        with connect(self.db_path) as connection:
            artist_id = upsert_artist(connection, "Test Artist")
            show = {
                "source_key": "event-a",
                "source_name": "test feed",
                "source_event_id": "1",
                "source_url": "https://example.com/event",
                "venue_as_reported": "Hellbender",
                "ticket_url": "https://tickets.example/show/1",
                "venue_id": "hellbender",
                "title": "Test Artist",
                "performance_start": (date.today()+timedelta(days=1)).isoformat()+"T18:30:00",
                "timezone": "America/New_York",
                "date_status": "feed_only",
                "date_note": "Feed date.",
                "performers": [{"name": "Test Artist", "role": "headliner", "confidence": 0.6, "note": "Parsed."}],
                "artist_spotify_links": {},
            }
            show_id = upsert_show(connection, show)
            add_metric_snapshot(connection, artist_id, followers=123, monthly_listeners=456, status="success")
            add_metric_snapshot(connection, artist_id, status="failed", detail="HTTP 429")

        row = get_review_rows(self.db_path)[0]
        self.assertEqual(row["followers"], 123)
        self.assertEqual(row["monthly_listeners"], 456)
        self.assertEqual(row["metric_status"], "failed")
        self.assertEqual(row["metric_detail"], "HTTP 429")

    def test_venue_coverage_includes_empty_venues(self):
        coverage = get_coverage(self.db_path)
        self.assertEqual(len(coverage), len(VENUES))
        self.assertTrue(all("show_count" in venue for venue in coverage))

    def test_sample_is_capped_and_covers_every_venue(self):
        events = []
        for venue_id in VENUES:
            for index in range(10):
                events.append(
                    {
                        "venue_id": venue_id,
                        "performance_start": "2026-10-{:02d}T20:00:00".format(index + 1),
                        "title": "Act {} {}".format(venue_id, index),
                        "performers": [
                            {"name": "Act {} {}".format(venue_id, index), "role": "headliner_candidate"}
                        ],
                    }
                )

        sample = select_validation_sample(events, max_artists=30, max_shows=25)
        distinct_artists = {
            performer["name"].casefold()
            for event in sample
            for performer in event["performers"]
            if performer["role"] != "band_member"
        }
        self.assertGreaterEqual(len(distinct_artists), 20)
        self.assertLessEqual(len(distinct_artists), 30)
        self.assertEqual({event["venue_id"] for event in sample}, set(VENUES))


if __name__ == "__main__":
    unittest.main()
