"""Repeatable event and metric collection for the validation prototype."""

import json
from collections import Counter
from typing import Dict

import requests
from concert_discovery.official_calendar import fetch_all_calendars

from concert_discovery.event_sources import (
    SOURCE_NAME,
    VENUES,
    fetch_upcoming_events,
    select_validation_sample,
)
from concert_discovery.spotify_public import fetch_public_artist_metrics
from concert_discovery.storage import (
    DATABASE_PATH,
    add_metric_snapshot,
    connect,
    initialize,
    upsert_show,
    utc_now,
)


def _start_run(connection, started_at: str) -> int:
    cursor = connection.execute(
        "INSERT INTO collection_runs (source_name, started_at, status) VALUES (?, ?, 'running')",
        (SOURCE_NAME, started_at),
    )
    return int(cursor.lastrowid)


def collect_artist_metric(artist_id: str, db_path=DATABASE_PATH, verified_metrics=None) -> Dict[str, object]:
    with connect(db_path) as connection:
        artist = connection.execute(
            "SELECT display_name, spotify_artist_id FROM artists WHERE artist_id=?",
            (artist_id,),
        ).fetchone()
    if not artist:
        raise ValueError("Unknown artist ID.")
    artist_name = str(artist["display_name"])
    with connect(db_path) as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='spotify_identity_evidence'").fetchone():
            evidence=connection.execute('SELECT profile_name FROM spotify_identity_evidence WHERE artist_id=? AND spotify_id=?',(artist_id,artist['spotify_artist_id'])).fetchone()
            if evidence:artist_name=evidence[0]
    spotify_id = artist["spotify_artist_id"]
    if not spotify_id:
        detail = "No Spotify profile is confirmed. Open Spotify search, choose the exact artist profile, then save its ID."
        with connect(db_path) as connection:
            add_metric_snapshot(connection, artist_id, status="unmatched", detail=detail)
        return {"status": "unmatched", "detail": detail}

    source_url = "https://open.spotify.com/artist/" + str(spotify_id)
    try:
        metrics = verified_metrics if verified_metrics is not None else fetch_public_artist_metrics(str(spotify_id), expected_name=artist_name)
        if metrics.get("monthly_listeners") is None:raise ValueError("Spotify profile matched, but monthly listeners were not supplied. Missing is not zero.")
    except requests.HTTPError as error:
        status = "rate_limited" if error.response is not None and error.response.status_code == 429 else "blocked" if error.response is not None and error.response.status_code == 403 else "http_error"
        detail = str(error)[:1000]
        with connect(db_path) as connection:
            add_metric_snapshot(connection, artist_id, status=status, detail=detail, source_url=source_url)
        return {"status": status, "detail": detail}
    except requests.RequestException as error:
        detail = str(error)[:1000]
        with connect(db_path) as connection:
            add_metric_snapshot(connection, artist_id, status="request_error", detail=detail, source_url=source_url)
        return {"status": "request_error", "detail": detail}
    except PermissionError as error:
        detail = str(error)[:1000]
        with connect(db_path) as connection:
            add_metric_snapshot(connection, artist_id, status="blocked", detail=detail, source_url=source_url)
        return {"status": "blocked", "detail": detail}
    except RuntimeError as error:
        detail = str(error)[:1000]
        with connect(db_path) as connection:
            add_metric_snapshot(connection, artist_id, status="rate_limited", detail=detail, source_url=source_url)
        return {"status": "rate_limited", "detail": detail}
    except ValueError as error:
        detail = str(error)[:1000]
        with connect(db_path) as connection:
            add_metric_snapshot(connection, artist_id, status="metrics_unavailable" if "monthly listeners were not supplied" in detail else "identity_or_parse_error", detail=detail, source_url=source_url)
        return {"status": "metrics_unavailable" if "monthly listeners were not supplied" in detail else "identity_or_parse_error", "detail": detail}

    with connect(db_path) as connection:
        if metrics.get('image_url'):
            connection.execute('''INSERT INTO artist_images VALUES(?,?,?,?) ON CONFLICT(artist_id)
                DO UPDATE SET image_url=excluded.image_url,source_url=excluded.source_url,updated_at=excluded.updated_at''',
                (artist_id,metrics['image_url'],metrics['source_url'],utc_now()))
        add_metric_snapshot(
            connection,
            artist_id,
            followers=metrics["followers"],
            monthly_listeners=metrics["monthly_listeners"],
            status="success",
            detail="Retrieved from public artist profile HTML via ordinary unauthenticated request.",
            source_url=metrics["source_url"],
        )
    return {"status": "success", **metrics}


def collect(days: int = 75, db_path=DATABASE_PATH) -> Dict[str, object]:
    initialize(db_path)
    started_at = utc_now()
    with connect(db_path) as connection:
        run_id = _start_run(connection, started_at)

    try:
        feed_events = fetch_upcoming_events(days=days)
        official_events,official_errors = fetch_all_calendars(days=days)
        official_error = '; '.join(official_errors) or None
        # Retain all shows. Sampling applies only to metric collection.
        events = feed_events + official_events
        metric_sample = select_validation_sample(events, max_artists=30, max_shows=25)
        sampled_names = {p["name"].casefold() for e in metric_sample for p in e["performers"]}
    except Exception as error:
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE collection_runs SET completed_at=?, status='failed', detail=? WHERE run_id=?",
                (utc_now(), str(error)[:1000], run_id),
            )
        return {
            "run_id": run_id,
            "status": "failed",
            "events_seen": 0,
            "shows_saved": 0,
            "metrics_ok": 0,
            "metrics_failed": 0,
            "artists_unmatched": 0,
            "detail": str(error),
        }

    feed_counts = Counter(event["venue_id"] for event in feed_events)
    sample_counts = Counter(event["venue_id"] for event in events)
    shows_saved = 0
    with connect(db_path) as connection:
        for event in events:
            show_id = upsert_show(connection, event)
            shows_saved += 1
        artists = connection.execute(
            """SELECT DISTINCT a.artist_id, a.display_name, a.spotify_artist_id
               FROM artists a JOIN show_artists sa USING (artist_id)
               JOIN shows s USING (show_id)
               WHERE s.performance_start >= date('now')
               ORDER BY a.display_name"""
        ).fetchall()
        connection.execute(
            "UPDATE collection_runs SET records_seen=?, records_saved=? WHERE run_id=?",
            (len(feed_events), shows_saved, run_id),
        )
        connection.executemany(
            """INSERT OR REPLACE INTO venue_source_coverage
               (run_id, venue_id, feed_events_found, sample_shows_saved)
               VALUES (?, ?, ?, ?)""",
            [
                (run_id, venue_id, feed_counts[venue_id], sample_counts[venue_id])
                for venue_id in VENUES
            ],
        )

    metrics_ok = 0
    metrics_failed = 0
    artists_unmatched = 0
    metric_errors = []
    for artist in artists:
        if artist["display_name"].casefold() not in sampled_names or not artist["spotify_artist_id"]:
            continue
        artist_id = str(artist["artist_id"])
        result = collect_artist_metric(artist_id, db_path)
        if result["status"] == "unmatched":
            artists_unmatched += 1
            continue
        if result["status"] == "success":
            metrics_ok += 1
        else:
            metrics_failed += 1
            metric_errors.append("{}: {}".format(artist["display_name"], result["detail"]))

    artists_unmatched = sum(1 for a in artists if not a["spotify_artist_id"])
    status = "partial" if metric_errors or artists_unmatched or official_error else "success"
    detail = json.dumps(
        {"metric_errors": metric_errors, "artists_unmatched": artists_unmatched, "window_days": days,
         "official_listings": len(official_events), "official_error": official_error,
         "metric_sample_artists": len(sampled_names)},
        ensure_ascii=False,
    )
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE collection_runs SET completed_at=?, status=?, detail=? WHERE run_id=?",
            (utc_now(), status, detail, run_id),
        )
    return {
        "run_id": run_id,
        "status": status,
        "events_seen": len(feed_events),
        "shows_saved": shows_saved,
        "artists_sampled": len(sampled_names),
        "metrics_ok": metrics_ok,
        "metrics_failed": metrics_failed,
        "artists_unmatched": artists_unmatched,
        "detail": detail,
    }


def main() -> None:
    result = collect()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
