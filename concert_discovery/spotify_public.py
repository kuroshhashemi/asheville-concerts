"""Experimental ordinary-HTTP parser for public Spotify artist profile pages.

This method is not the Spotify Web API and conflicts with Spotify's published
developer policy. It is isolated so it can be removed if access is blocked or
the policy risk is unacceptable. It uses plain requests only: no login, custom
TLS impersonation, proxies, CAPTCHA handling, or private API calls.
"""

import base64
import json
import re
import unicodedata
from html.parser import HTMLParser
from typing import Dict, Optional

import requests


PROFILE_URL = "https://open.spotify.com/artist/{}"
PROFILE_ID = re.compile(r"^[A-Za-z0-9]{22}$")


class _InitialStateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_initial_state = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "initialState":
            self.in_initial_state = True

    def handle_endtag(self, tag):
        if tag == "script" and self.in_initial_state:
            self.in_initial_state = False

    def handle_data(self, data):
        if self.in_initial_state:
            self.parts.append(data)


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", normalized.casefold())


def _decode_state(markup: str) -> dict:
    parser = _InitialStateParser()
    parser.feed(markup)
    encoded = "".join(parser.parts).strip()
    if not encoded:
        raise ValueError("Spotify profile has no initialState payload.")
    padded = encoded + ("=" * (-len(encoded) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        try:
            return json.loads(encoded)
        except json.JSONDecodeError as error:
            raise ValueError("Spotify initialState payload format changed.") from error


def fetch_public_artist_metrics(
    spotify_artist_id: str, expected_name: Optional[str] = None
) -> Dict[str, object]:
    if not PROFILE_ID.fullmatch(spotify_artist_id):
        raise ValueError("Spotify artist ID must be 22 letters or digits.")

    url = PROFILE_URL.format(spotify_artist_id)
    response = requests.get(url, timeout=25)
    if response.status_code == 403:
        raise PermissionError("Spotify returned HTTP 403 for this public artist page.")
    if response.status_code == 429:
        raise RuntimeError("Spotify rate-limited the ordinary page request (HTTP 429).")
    response.raise_for_status()

    payload = _decode_state(response.text)
    entity_key = "spotify:artist:" + spotify_artist_id
    entity = payload.get("entities", {}).get("items", {}).get(entity_key)
    if not isinstance(entity, dict):
        raise ValueError("Spotify profile payload did not contain the requested artist ID.")

    profile = entity.get("profile", {})
    stats = entity.get("stats", {})
    found_name = str(profile.get("name", ""))
    if expected_name and _name_key(found_name) != _name_key(expected_name):
        raise ValueError(
            "Spotify profile name {!r} does not match confirmed artist {!r}.".format(
                found_name, expected_name
            )
        )

    followers = stats.get("followers")
    monthly_listeners = stats.get("monthlyListeners")
    if not isinstance(followers, int) or not isinstance(monthly_listeners, int):
        raise ValueError("Spotify profile is missing follower or monthly-listener metrics.")

    return {
        "spotify_artist_id": spotify_artist_id,
        "name": found_name,
        "followers": followers,
        "monthly_listeners": monthly_listeners,
        "source_url": url,
        "image_url": next((i.get('url') for i in entity.get('visuals',{}).get('avatarImage',{}).get('sources',[]) if i.get('url')),None),
    }
