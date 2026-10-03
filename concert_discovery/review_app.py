"""Minimal artist-review page for Asheville concert discovery.

Run:  .venv/bin/streamlit run concert_discovery/review_app.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import streamlit as st

# ── path hygiene so imports work from any CWD ──────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from concert_discovery.collector import collect_artist_metric
from concert_discovery.storage import (
    DATABASE_PATH,
    clear_artist_spotify_match,
    confirm_candidate_match,
    get_artists,
    get_coverage,
    get_review_rows,
    initialize,
    save_manual_spotify_match,
)

# ── constants ────────────────────────────────────────────────────────────────
SPOTIFY_ID_RE = re.compile(r"[A-Za-z0-9]{22}")
SPOTIFY_URL_RE = re.compile(r"open\.spotify\.com/artist/([A-Za-z0-9]{22})")

STATUS_LABELS = {
    "candidate":        "🟡 Candidate",
    "manual_confirmed": "✅ Confirmed",
    "unresolved":       "⬜ Unresolved",
    "source_link":      "🔗 Source link",
}
STATUS_ORDER = ["manual_confirmed", "candidate", "unresolved", "source_link"]

ALL_VENUES = {
    "asheville-music-hall": "Asheville Music Hall",
    "eulogy":               "Eulogy",
    "hellbender":           "Hellbender",
    "grey-eagle":           "The Grey Eagle",
    "orange-peel":          "The Orange Peel",
}

# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_spotify_id(raw: str) -> Optional[str]:
    raw = raw.strip()
    m = SPOTIFY_URL_RE.search(raw)
    if m:
        return m.group(1)
    if SPOTIFY_ID_RE.fullmatch(raw):
        return raw
    return None


def _fmt_number(n) -> str:
    if n is None:
        return "—"
    return f"{int(n):,}"


def _metric_label(status: str) -> str:
    icons = {
        "success": "✅",
        "unresolved": "⬜",
        "unmatched": "⬜",
        "rate_limited": "⏳",
        "blocked": "🚫",
        "http_error": "❌",
        "identity_or_parse_error": "⚠️",
        "request_error": "❌",
    }
    return icons.get(status, "?") + " " + status


# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Asheville Concert Discovery · Review",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container { padding: 1rem 1.2rem 2rem; max-width: 900px; margin: auto; }
    .stExpander { border: 1px solid #ddd; border-radius: 6px; margin-bottom: .5rem; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    @media (max-width: 600px) {
        .block-container { padding: .5rem .6rem 2rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── initialise DB (idempotent, no network) ───────────────────────────────────
initialize()

# ── flash messages from previous actions ─────────────────────────────────────
for key in ("flash_ok", "flash_warn", "flash_err"):
    msg = st.session_state.pop(key, None)
    if msg:
        {"flash_ok": st.success, "flash_warn": st.warning, "flash_err": st.error}[key](msg)

# ── title ────────────────────────────────────────────────────────────────────
st.title("🎵 Asheville Concert Discovery")
st.caption(
    "Artist matching review · candidate Spotify links · on-demand metric collection  \n"
    f"Database: `{DATABASE_PATH}`"
)
st.info(
    "**Note:** Spotify metrics are fetched from ordinary public artist pages on demand. "
    "No automatic network requests run on page refresh.",
    icon="ℹ️",
)

# ── load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def _load():
    rows = get_review_rows()          # all artists, no limit
    coverage = get_coverage()
    return rows, coverage

rows, coverage = _load()

# ── sidebar / filters ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    venue_opts = ["All venues"] + list(ALL_VENUES.values())
    sel_venue = st.selectbox("Venue", venue_opts)

    status_opts = ["All statuses"] + [STATUS_LABELS[s] for s in STATUS_ORDER]
    sel_status = st.selectbox("Match status", status_opts)
    st.divider()
    st.caption(f"Total artists: {len(rows)}")

# ── venue coverage table ──────────────────────────────────────────────────────
with st.expander("📍 Collection details · coverage still being validated", expanded=False):
    st.caption("Saved shows include all collected listings. Feed counts are not a completeness measure. Orange Peel/Hellbender also use the official calendar; other venues are not yet independently verified.")
    for v in coverage:
        sc = v["show_count"]
        fe = v.get("feed_events_found", "?")
        st.markdown(
            f"**{v['name']}** — {sc} saved show(s) · "
            f"{fe} aggregate-feed listing(s) · [calendar]({v['official_url']})"
        )
        if v.get("coverage_note"):
            st.caption(v["coverage_note"])

st.divider()

# ── apply filters ─────────────────────────────────────────────────────────────
def _venue_id_for_name(name: str) -> Optional[str]:
    for vid, vname in ALL_VENUES.items():
        if vname == name:
            return vid
    return None

filtered = rows
if sel_venue != "All venues":
    target_vid = _venue_id_for_name(sel_venue)
    filtered = [r for r in filtered if any(s["venue_id"] == target_vid for s in r.get("shows", []))]

if sel_status != "All statuses":
    target_status = next(k for k, v in STATUS_LABELS.items() if v == sel_status)
    filtered = [r for r in filtered if r.get("match_status") == target_status]

st.subheader(f"Artists ({len(filtered)} shown)")

# ── per-artist cards ──────────────────────────────────────────────────────────
for row in filtered:
    aid = row["artist_id"]
    name = row["display_name"]
    status = row.get("match_status", "unresolved")
    label = STATUS_LABELS.get(status, status)
    spotify_id = row.get("spotify_artist_id")
    profile_url = row.get("spotify_profile_url")
    evidence = row.get("match_reason") or ""
    followers = row.get("followers")
    listeners = row.get("monthly_listeners")
    metric_ts = row.get("metric_retrieved_at")
    metric_status = row.get("metric_status") or ""
    shows: list = row.get("shows", [])

    # derive earliest show date + all venues for subtitle
    dates = sorted(set(s["performance_start"][:10] for s in shows))
    venues = sorted(set(s["venue_name"] for s in shows))
    subtitle = f"{label} · {', '.join(venues)} · {', '.join(dates)}"

    with st.expander(f"**{name}** — {subtitle}", expanded=(status in ("candidate", "manual_confirmed"))):

        # ── shows sub-table ───────────────────────────────────────────────────
        st.markdown("**Shows**")
        for s in shows:
            show_date = s["performance_start"][:16].replace("T", " ")
            role = s.get("billing_role") or "?"
            src = s.get("source_url") or s.get("venue_calendar_url") or ""
            tkt = s.get("ticket_url") or ""
            official = s.get("official_event_url") or ""

            links = []
            if src:
                links.append(f"[source listing]({src})")
            if official:
                links.append(f"[venue page]({official})")
            if tkt:
                links.append(f"[tickets]({tkt})")
            link_str = " · ".join(links) if links else "no links"

            st.markdown(
                f"- **{s['venue_name']}** · {show_date} · *{role}* · {link_str}"
            )

        st.divider()

        # ── spotify match section ─────────────────────────────────────────────
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"**Spotify match status:** {label}")
            if spotify_id:
                st.markdown(f"**Profile:** [{spotify_id}]({profile_url})")
            if evidence:
                st.caption(f"Evidence: {evidence}")

        with col2:
            if not spotify_id:
                search_url = f"https://open.spotify.com/search/{name.replace(' ', '%20')}"
                st.link_button("Search Spotify →", search_url)

        # ── metrics ───────────────────────────────────────────────────────────
        if spotify_id and followers is not None:
            is_candidate = status in ("candidate",)
            metric_note = "⚠️ Unverified candidate metrics" if is_candidate else ""
            if metric_note:
                st.warning(metric_note, icon="⚠️")
            mcols = st.columns(3)
            mcols[0].metric("Followers", _fmt_number(followers))
            mcols[1].metric("Monthly listeners", _fmt_number(listeners))
            mcols[2].metric(
                "Retrieved",
                metric_ts[:10] if metric_ts else "—",
                help=metric_ts,
            )
        elif spotify_id and metric_status and metric_status not in ("unresolved", "unmatched", ""):
            st.caption(f"Last metric attempt: {_metric_label(metric_status)}")

        st.divider()

        # ── action buttons ────────────────────────────────────────────────────
        btn_cols = st.columns([1, 1, 1])

        # Fetch metrics button (only if has a Spotify ID, network needed)
        with btn_cols[0]:
            if spotify_id:
                if st.button("📡 Fetch metrics", key=f"fetch_{aid}"):
                    with st.spinner(f"Fetching metrics for {name}…"):
                        result = collect_artist_metric(aid)
                    if result["status"] == "success":
                        st.session_state["flash_ok"] = (
                            f"✅ {name}: {_fmt_number(result['followers'])} followers · "
                            f"{_fmt_number(result['monthly_listeners'])} monthly listeners"
                        )
                    else:
                        st.session_state["flash_warn"] = f"⚠️ {name}: {result['detail']}"
                    _load.clear()
                    st.rerun()

        # Confirm candidate button
        with btn_cols[1]:
            if status == "candidate":
                if st.button("✅ Confirm match", key=f"confirm_{aid}"):
                    confirm_candidate_match(aid)
                    st.session_state["flash_ok"] = f"Confirmed Spotify match for {name}."
                    _load.clear()
                    st.rerun()

        # Clear match button (resets to unresolved)
        with btn_cols[2]:
            if spotify_id:
                if st.button("🗑 Clear match", key=f"clear_{aid}"):
                    clear_artist_spotify_match(aid)
                    st.session_state["flash_ok"] = f"Cleared Spotify match for {name}."
                    _load.clear()
                    st.rerun()

        # Paste / correct Spotify URL form
        with st.form(key=f"form_{aid}", clear_on_submit=True):
            raw = st.text_input(
                "Paste Spotify artist URL or 22-char ID to set / correct match:",
                placeholder="https://open.spotify.com/artist/…",
                label_visibility="visible",
            )
            submitted = st.form_submit_button("💾 Save as confirmed match")

        if submitted:
            parsed = _parse_spotify_id(raw)
            if not parsed:
                st.error("Couldn't parse a Spotify artist ID from that input.")
            else:
                try:
                    save_manual_spotify_match(aid, parsed)
                    st.session_state["flash_ok"] = (
                        f"Saved confirmed match for {name}: {parsed}"
                    )
                    _load.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error saving match: {exc}")

# ── footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Metric values are point-in-time observations. "
    "A missing value means unknown or unavailable, never zero. "
    "Candidate metrics are from unverified Spotify profiles and should not be used for ranking."
)
