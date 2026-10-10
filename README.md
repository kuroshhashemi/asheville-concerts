# Asheville Soundcheck

Discover Asheville shows. Listen on Spotify, find rising artists, and save your next night out.

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

## Weekly email digest

Optional Monday email of newly discovered shows, with the same catalog visibility rules
and artist/venue/genre/listener/growth/price/link data as the site. Personal filters do not
apply. Empty weeks send no email. First scheduled digest: October 19, 2026, around
9 a.m. America/New_York (GitHub may delay scheduled jobs).

Run setup_digest.sql in the existing Supabase project. Subscriptions and delivery records
are private server-only tables with row-level security; they are never put in the catalog.
Signed-in visitors opt in under Emails. Every email includes an unsubscribe confirmation
link that works without signing in. Existing subscriptions start opted out.

The weekly-digest workflow needs encrypted Actions secrets EMAIL_SENDER,
EMAIL_APP_PASSWORD, SUPABASE_URL, and SUPABASE_SECRET_KEY. Use a Gmail app password,
never a regular Google password. Its manual default is preview; test mode sends only to
the sender. Send mode honors the Monday/start-date gate. Duplicate delivery claims and
sent show keys prevent resends; uncertain SMTP outcomes require review instead of blind
retries. A 200-recipient safeguard keeps this small personal deployment bounded.
No AI models, event APIs, or new scraping calls run during digest generation.
