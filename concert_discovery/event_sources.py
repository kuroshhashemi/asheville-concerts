"""Public event-feed collector. It does not crawl around source protections."""

from datetime import date, datetime, time, timedelta
from html import unescape
from html.parser import HTMLParser
import re
from typing import Dict, List, Optional, Tuple

import requests


SOURCE_NAME = "LiveMusicAsheville"
EVENTS_API = "https://livemusicasheville.com/wp-json/tribe/events/v1/events"

VENUES = {
    'one-stop':dict(name='The One Stop',official_url='https://ashevillemusichall.com/',aliases=('one stop',),note='Separate room from Music Hall.'),
    'harrahs-arena':dict(name='Harrah’s Cherokee Center · Arena',official_url='https://www.harrahscherokeecenterasheville.com/events-tickets/',aliases=('exploreasheville.com arena',),note='Arena within Harrah’s Cherokee Center.'),
    'thomas-wolfe':dict(name='Thomas Wolfe Auditorium',official_url='https://www.harrahscherokeecenterasheville.com/events-tickets/',aliases=('thomas wolfe',),note='Auditorium within Harrah’s Cherokee Center.'),
    'sierra-nevada':dict(name='Sierra Nevada · Mills River',official_url='https://sierranevada.com/events/mills-river',aliases=('sierra nevada',),note='Mills River only.'),
    "asheville-music-hall": {
        "name": "Asheville Music Hall",
        "official_url": "https://ashevillemusichall.com/",
        "aliases": ("asheville music hall",),
        "note": "The calendar also includes The One Stop; inspect each event's room label.",
    },
    "eulogy": {
        "name": "Eulogy",
        "official_url": "https://burialbeer.com/pages/eulogy",
        "aliases": ("eulogy",),
        "note": "The official calendar is DICE-powered and contained more listings than the city feed sample.",
    },
    "hellbender": {
        "name": "Hellbender",
        "official_url": "https://hellbenderavl.com/",
        "aliases": ("hellbender",),
        "note": "Promoted by The Orange Peel; its own event listings are cross-posted on Orange Peel pages.",
    },
    "grey-eagle": {
        "name": "The Grey Eagle",
        "official_url": "https://www.thegreyeagle.com/",
        "aliases": ("grey eagle",),
        "note": "Listings can be at the main hall or patio; preserve the source's room name when present.",
    },
    "orange-peel": {
        "name": "The Orange Peel",
        "official_url": "https://theorangepeel.net/",
        "aliases": ("orange peel",),
        "note": "The promoter's calendar also cross-lists Hellbender shows; use the event's physical venue.",
    },
}

OFFICIAL_EVENT_CHECKS = {
    "the midnight: time machines w/ bonnie mckee": (
        "https://theorangepeel.net/event/the-midnight-time-machines/the-orange-peel/asheville-north-carolina/",
        [("The Midnight", "headliner", 0.99), ("Bonnie McKee", "support", 0.99)],
    ),
    "patio show: meryljane": (
        "https://www.thegreyeagle.com/event/patio-show-meryljane/the-patio/asheville-north-carolina/",
        [("MerylJane", "headliner", 1.0)],
    ),
    "dylan gossett & charles wesley godwin": (
        "https://hellbenderavl.com/event/dylan-gossett-charles-wesley-godwin/hellbender/",
        [("Dylan Gossett", "co-headliner", 0.99), ("Charles Wesley Godwin", "co-headliner", 0.99), ("Max Alan", "support", 0.98)],
    ),
    "perūze ft. reggie headen, brandon phelps, andré lassalle and lenny pettinelli": (
        "https://ashevillemusichall.com/event/per%C5%ABze/asheville-music-hall-live-music/",
        [("Perūze", "headliner", 1.0)],
    ),
    "white denim w/ arc iris": (
        "https://burialbeer.com/pages/eulogy",
        [("White Denim", "headliner", 0.95), ("Arc Iris", "support", 0.9)],
    ),
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3,
    "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6,
    "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
DATE_MENTION = re.compile(
    r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
SPOTIFY_ARTIST_URL = re.compile(r"https?://open\.spotify\.com/artist/([A-Za-z0-9]{22})", re.I)


class _MarkupParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: List[str] = []
        self.links: List[Tuple[str, str]] = []
        self.anchor_href: Optional[str] = None
        self.anchor_text: List[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "a":
            self.anchor_href = attrs.get("href")
            self.anchor_text = []

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        if tag == "a" and self.anchor_href:
            label = " ".join(self.anchor_text).strip()
            self.links.append((label, self.anchor_href))
            self.anchor_href = None
            self.anchor_text = []

    def handle_data(self, data):
        if self.hidden:
            return
        clean = data.strip()
        if clean:
            self.text.append(clean)
            if self.anchor_href:
                self.anchor_text.append(clean)


def normalize(value: str) -> str:
    return " ".join(unescape(value or "").casefold().split())


def venue_id_for(source_venue) -> Optional[str]:
    if isinstance(source_venue, dict):
        source_name = str(source_venue.get("venue", ""))
    else:
        source_name = str(source_venue or "")
    value = normalize(source_name)
    if 'one stop' in value:return 'one-stop'
    if 'hellbender' in value:return 'hellbender'
    matches = [
        venue_id for venue_id, venue in VENUES.items()
        if any(alias in value for alias in venue["aliases"])
    ]
    return matches[0] if len(matches) == 1 else None


def parse_performers(title: str) -> List[Dict[str, object]]:
    clean = unescape(title or "").strip()
    checked = OFFICIAL_EVENT_CHECKS.get(normalize(clean))
    if checked:
        return [
            {"name": name, "role": role, "confidence": confidence, "note": "Manually checked against the official venue listing."}
            for name, role, confidence in checked[1]
        ]

    if "sort of damocles" in normalize(clean):
        return [{
            "name": "Sort of Damocles",
            "role": "headliner_candidate",
            "confidence": 0.62,
            "note": "The title describes a Rocky Horror-themed show; verify Sort of Damocles is the billed performing act.",
        }]
    if re.search(r"womyn rising|artisan market|community celebration", clean, re.I):
        return []
    clean = re.sub(r"^(?:free show\s*[–—-]\s*|(?:free\s+)?patio(?:\s+show)?:\s*)", "", clean, flags=re.I)
    clean = re.sub(r"^eulogy presents:\s*", "", clean, flags=re.I)
    clean = re.sub(r"^coming\s+[^|]+\|\s*", "", clean, flags=re.I)
    clean = re.sub(r'\s*\((?:DJ Set|Album Release|Night \d|Both Nights)[^)]*\)\s*','',clean,flags=re.I)
    clean = re.split(r'\s*[:–]\s*',clean)[0]
    clean = re.sub(r'\s+(?:Farewell tour|Annual Thanksgiving Homecoming Concert|Album Release|Family Jamboree|Birthday Celebration).*','',clean,flags=re.I)
    marker = re.search(r"\s+(w/|with|ft\.?|feat\.?|featuring)\s+", clean, re.I)
    if marker:
        headliner = clean[:marker.start()].strip(" :–—-")
        support = clean[marker.end():].strip()
        role = "featured" if marker.group(1).casefold().startswith(("ft", "feat")) else "support"
        acts = [{"name": headliner, "role": "headliner_candidate", "confidence": 0.82, "note": "Headliner parsed from explicit billing marker."}]
        support_names = re.split(r",|\s+&\s+|\s+and\s+|\s*\+\s*", support)
        acts.extend(
            {"name": name.strip(" .–—-"), "role": role, "confidence": 0.78, "note": "Support/featured billing parsed from event title."}
            for name in support_names if name.strip(" .–—-")
        )
        return acts

    if " + " in clean or clean=='Wednesday & Mannequin Pussy':
        names = [name.strip() for name in re.split(r"\s+[+&]\s+", clean) if name.strip()]
        if len(names) > 1:
            return [
                {"name": name, "role": "co-headliner_candidate", "confidence": 0.62, "note": "Ampersand title parsed as co-headliners; verify billing."}
                for name in names
            ]

    if not clean or re.search(r"open mic|trivia|market|jam night|dance party", clean, re.I):
        return []
    return [{"name": clean, "role": "headliner_candidate", "confidence": 0.55, "note": "Single event title treated as artist candidate; verify it is a performer."}]


def check_date(title: str, performance_start: str) -> Tuple[str, str]:
    show_date = date.fromisoformat(performance_start[:10])
    mentions = [
        (MONTHS[match.group(1).casefold()], int(match.group(2)))
        for match in DATE_MENTION.finditer(unescape(title or ""))
    ]
    if any(item != (show_date.month, show_date.day) for item in mentions):
        return "date_conflict", "The title advertises a different date than the feed's performance date."
    if normalize(title) in OFFICIAL_EVENT_CHECKS:
        return "venue_confirmed", "Title and date spot-checked against the official venue event page."
    return "feed_only", "Performance date is the feed start_date; not independently checked at the venue."


def extract_artist_spotify_links(links: List[Tuple[str, str]]) -> Dict[str, str]:
    matches = {}
    for label, href in links:
        found = SPOTIFY_ARTIST_URL.search(href)
        if found and label.strip():
            matches[normalize(label)] = found.group(1)
    return matches


def _ticket_url(links: List[Tuple[str, str]]) -> Optional[str]:
    for label, href in links:
        lowered = (label + " " + href).casefold()
        if any(site in lowered for site in ("dice.fm", "etix.com", "ticketmaster.com", "ticketweb.com")):
            return href
    return None


def fetch_upcoming_events(days: int = 75, today: Optional[date] = None) -> List[dict]:
    today = today or datetime.now().date()
    start = datetime.combine(today, time.min)
    end = start + timedelta(days=days)
    params = {
        "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
        "per_page": 50,
        "page": 1,
        "status": "publish",
    }
    response = requests.get(EVENTS_API, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    total_pages = min(int(payload.get("total_pages", 1)), 80)
    raw_events = list(payload.get("events", []))
    for page in range(2, total_pages + 1):
        params["page"] = page
        page_response = requests.get(EVENTS_API, params=params, timeout=45)
        page_response.raise_for_status()
        raw_events.extend(page_response.json().get("events", []))

    events = []
    for event in raw_events:
        venue_id = venue_id_for(event.get("venue"))
        if not venue_id:
            continue
        performance_start = str(event.get("start_date", ""))
        try:
            performance_date = datetime.fromisoformat(performance_start).date()
        except ValueError:
            continue
        if performance_date < today or performance_date > end.date():
            continue
        title = unescape(str(event.get("title", ""))).strip()
        parser = _MarkupParser()
        description = str(event.get("description", ""))
        parser.feed(description)
        date_status, date_note = check_date(title, performance_start)
        official_check = OFFICIAL_EVENT_CHECKS.get(normalize(title))
        event_id = str(event.get("id", ""))
        source_key = "{}:{}:{}".format(SOURCE_NAME, event_id, performance_start)
        events.append({
            "source_key": source_key,
            "source_name": SOURCE_NAME,
            "source_event_id": event_id,
            "source_url": str(event.get("url", "")),
            "official_event_url": official_check[0] if official_check else None,
            "venue_id": venue_id,
            "venue_as_reported": (
                event.get("venue", {}).get("venue", "")
                if isinstance(event.get("venue"), dict)
                else str(event.get("venue", ""))
            ),
            "title": title,
            "performance_start": performance_start,
            "timezone": str(event.get("timezone", "")),
            "ticket_url": _ticket_url(parser.links),
            "date_status": date_status,
            "date_note": date_note,
            "artist_spotify_links": extract_artist_spotify_links(parser.links),
            "performers": parse_performers(title),
        })
    return sorted(events, key=lambda event: (event["performance_start"], event["venue_id"], event["title"]))


def select_validation_sample(events: List[dict], max_artists: int = 30, max_shows: int = 25) -> List[dict]:
    """Select a small, venue-balanced review sample without splitting bills."""
    by_venue = {venue_id: [] for venue_id in VENUES}
    for event in events:
        by_venue.setdefault(event["venue_id"], []).append(event)
    for venue_events in by_venue.values():
        venue_events.sort(key=lambda event: (event["performance_start"], event["title"]))

    positions = {venue_id: 0 for venue_id in by_venue}
    selected = []
    unique_artists = set()
    venue_order = list(VENUES)
    while len(selected) < max_shows:
        added_in_round = False
        for venue_id in venue_order:
            venue_events = by_venue.get(venue_id, [])
            while positions[venue_id] < len(venue_events):
                event = venue_events[positions[venue_id]]
                positions[venue_id] += 1
                billed = {
                    performer["name"].casefold()
                    for performer in event["performers"]
                    if performer["role"] != "band_member"
                }
                if not billed:
                    continue
                expanded = unique_artists | billed
                if len(expanded) > max_artists:
                    continue
                selected.append(event)
                unique_artists = expanded
                added_in_round = True
                break
            if len(selected) >= max_shows:
                break
        if not added_in_round:
            break
    return sorted(selected, key=lambda event: (event["performance_start"], event["venue_id"], event["title"]))
