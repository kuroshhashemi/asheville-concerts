# Asheville Soundcheck

A Streamlit concert table with venue and status filters, Spotify monthly listeners,
inline artwork, and audience comparison bars.

## Run

Install requirements.txt, then run:

    streamlit run concert_discovery/shortlist_app.py

The web app reads a shared catalog; it never calls paid event APIs during browsing.
Google login saves personal statuses and filters in Supabase across devices.
Anonymous browser filters are stored locally. New visitors start with Live Music only,
at least 500k Spotify listeners, and unknown listener counts hidden.
Do not use local SQLite as a durable multiuser cloud database.

## Scheduled collection

The GitHub Actions workflow refreshes events daily and only refreshes each artist's
Spotify observations when its latest success is at least seven days old. Artist identity
lookups are bounded and failed lookups have a seven-day cooldown.

Add JAMBASE_API_KEY and TICKETMASTER_API_KEY as repository Actions secrets.
No API credentials belong in the repository. The JamBase request ledger is committed
with catalog updates and permits at most 900 attempts within a rolling 32-day window.
It starts with the five research calls already made. Failed requests also count.
This protects requests made by this app; other tools using the same key have to share
this ledger or use a separate safety allowance.

Official calendars, Songkick, Bandsintown browser calendars, JamBase and Ticketmaster
are aggregated. Unavailable sources retain cached records; coverage is not guaranteed.
Conflicting room/date data requires review. Public Spotify HTML and widget endpoints
may change; unknown metrics remain missing and are never invented.

Six-month growth requires an actual six-month baseline; the prototype does not create
historical listener numbers. Automated collection contains no model calls.
