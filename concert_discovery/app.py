"""Local review UI for Asheville concert-source and Spotify-metric validation."""

import re
from urllib.parse import quote

import pandas as pd
import streamlit as st

from concert_discovery.collector import collect, collect_artist_metric
from concert_discovery.event_sources import VENUES
from concert_discovery.storage import (
    DATABASE_PATH,
    add_metric_snapshot,
    connect,
    get_artists,
    get_coverage,
    get_latest_run,
    get_review_rows,
    initialize,
    save_manual_spotify_match,
    utc_now,
)


SPOTIFY_ID_PATTERN = re.compile(r"open\.spotify\.com/artist/([A-Za-z0-9]{22})")


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def load_review_data():
    initialize()
    run = get_latest_run()
    if run is None or run["status"] == "failed":
        collect()
    return get_review_rows(limit=30), get_coverage(), get_latest_run(), get_artists()


def spotify_id_from_input(value: str) -> str:
    value = value.strip()
    match = SPOTIFY_ID_PATTERN.search(value)
    candidate = match.group(1) if match else value
    if not re.fullmatch(r"[A-Za-z0-9]{22}", candidate):
        raise ValueError("Paste a Spotify artist profile URL or its 22-character artist ID.")
    return candidate


def save_failed_metric(artist_id: str, spotify_id: str, status: str, detail: str) -> None:
    with connect() as connection:
        add_metric_snapshot(
            connection,
            artist_id,
            status=status,
            detail=detail[:1000],
            source_url="https://open.spotify.com/artist/" + spotify_id,
        )


st.set_page_config(page_title="Asheville Concert Discovery", page_icon="♫", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');
    :root { --ink: #18352f; --muted: #687b75; --paper: #f5f7f2; --line: #dce4dc; --green: #276b57; --amber: #a36b06; }
    .stApp { background: var(--paper); color: var(--ink); }
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    h1, h2, h3 { color: var(--ink); }
    h1 { font-family: 'Newsreader', Georgia, serif; font-size: 2.4rem; letter-spacing: 0; }
    [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 4px; }
    [data-testid="stMetric"] { border-top: 2px solid var(--green); padding-top: .45rem; }
    @media (max-width: 640px) { h1 { font-size: 2rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Asheville Concert Discovery")
st.caption("Upcoming shows · artist identity review · dated audience metrics")
st.warning(
    "Spotify's official Web API does not provide monthly listeners, and Spotify's developer policy prohibits scraping. "
    "This personal validation prototype uses ordinary unauthenticated requests to public artist pages only, as requested. "
    "It may break or be rate-limited; no login, proxy, CAPTCHA bypass, or hidden API is used."
)

initialize()
last_result = st.session_state.pop("last_metric_result", None)
if last_result:
    if last_result["status"] == "success":
        st.success("Saved a Spotify metric snapshot for " + last_result["artist"] + ".")
    else:
        st.warning(last_result["artist"] + ": " + last_result["detail"])

if st.button("Refresh shows and matched Spotify metrics", type="primary", width="stretch"):
    with st.spinner("Checking upcoming venue listings and confirmed Spotify profiles..."):
        result = collect()
    load_review_data.clear()
    st.session_state["refresh_result"] = result
    st.rerun()

refresh_result = st.session_state.pop("refresh_result", None)
if refresh_result:
    st.info(
        "Collection {}: {} feed listings, {} performers, {} metric successes, {} metric failures, {} unmatched."
        .format(
            refresh_result["status"],
            refresh_result["events_seen"],
            refresh_result["shows_saved"],
            refresh_result["metrics_ok"],
            refresh_result["metrics_failed"],
            refresh_result["artists_unmatched"],
        )
    )

try:
    review_rows, coverage_rows, run, artist_rows = load_review_data()
except Exception as error:
    st.error("Could not load concert data: " + str(error))
    st.stop()

if run:
    st.caption(
        "Last collection: {} · {} · Local database: {}".format(
            run["completed_at"] or run["started_at"], run["status"], DATABASE_PATH.name
        )
    )

st.subheader("Venue coverage")
coverage = pd.DataFrame(coverage_rows)
if not coverage.empty:
    coverage = coverage.rename(
        columns={
            "name": "Venue",
            "show_count": "Shows in sample",
            "first_show": "First date",
            "last_show": "Last date",
            "coverage_note": "Coverage note",
            "official_url": "Venue calendar",
        }
    )
    st.dataframe(
        coverage[["Venue", "Shows in sample", "First date", "Last date", "Coverage note", "Venue calendar"]],
        width="stretch",
        hide_index=True,
        column_config={"Venue calendar": st.column_config.LinkColumn(display_text="Open venue")},
    )

st.subheader("Upcoming performers")
if review_rows:
    table = pd.DataFrame(review_rows).rename(
        columns={
            "display_name": "Artist",
            "venue_name": "Venue",
            "performance_start": "Show date/time",
            "title": "Show",
            "billing_role": "Billing role",
            "spotify_profile_url": "Spotify profile",
            "spotify_search_url": "Spotify match search",
            "followers": "Followers",
            "monthly_listeners": "Monthly listeners",
            "metric_retrieved_at": "Metrics retrieved",
            "metric_status": "Metric status",
            "metric_detail": "Metric note",
            "match_status": "Match status",
            "match_confidence": "Match confidence",
            "match_reason": "Match reason",
            "role_confidence": "Role confidence",
            "date_status": "Date status",
            "date_note": "Date note",
            "ticket_url": "Tickets",
            "source_url": "Listing source",
        }
    )
    columns = [
        "Artist", "Venue", "Show date/time", "Show", "Billing role",
        "Spotify profile", "Spotify match search", "Followers", "Monthly listeners",
        "Metrics retrieved", "Metric status", "Metric note", "Match status",
        "Match confidence", "Match reason", "Role confidence", "Date status",
        "Date note", "Tickets", "Listing source",
    ]
    st.dataframe(
        table[[column for column in columns if column in table]],
        width="stretch",
        hide_index=True,
        height=min(720, 46 + 38 * (len(table) + 1)),
        column_config={
            "Spotify profile": st.column_config.LinkColumn(display_text="Profile"),
            "Spotify match search": st.column_config.LinkColumn(display_text="Search Spotify"),
            "Tickets": st.column_config.LinkColumn(display_text="Tickets"),
            "Listing source": st.column_config.LinkColumn(display_text="Source"),
            "Followers": st.column_config.NumberColumn(format="%d"),
            "Monthly listeners": st.column_config.NumberColumn(format="%d"),
            "Match confidence": st.column_config.NumberColumn(format="%.2f"),
            "Role confidence": st.column_config.NumberColumn(format="%.2f"),
        },
    )
else:
    st.info("No artist rows are available yet. Use Refresh to retry the public event feed.")

with st.expander("Confirm or correct a Spotify artist match"):
    if not artist_rows:
        st.info("Refresh the event source before matching artists.")
    else:
        names = {artist["artist_id"]: artist["display_name"] for artist in artist_rows}
        selected_id = st.selectbox(
            "Artist to match",
            list(names),
            format_func=lambda artist_id: names[artist_id],
        )
        st.link_button(
            "Search this artist on Spotify",
            "https://open.spotify.com/search/" + quote(names[selected_id]),
        )
        with st.form("spotify_match_form", clear_on_submit=True):
            entered_id = st.text_input(
                "Paste exact Spotify artist profile URL or 22-character ID"
            )
            submitted = st.form_submit_button("Save confirmed match and fetch metrics")
        if submitted:
            try:
                spotify_id = spotify_id_from_input(entered_id)
                save_manual_spotify_match(selected_id, spotify_id)
                result = collect_artist_metric(selected_id)
            except Exception as error:
                st.error("Could not save/fetch this match: " + str(error))
            else:
                result["artist"] = names[selected_id]
                st.session_state["last_metric_result"] = result
                load_review_data.clear()
                st.rerun()

st.caption(
    "Metric values are dated observations, not trend estimates. A missing value means unknown/unavailable, never zero. "
    "Refresh repeatedly to accumulate snapshots; trend calculations are deliberately deferred."
)
