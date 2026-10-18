import re
import time
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
from django.conf import settings

from tracker.providers.base import ActivityType, FetchedActivity, Provider, SyncError, fetch_cutoff

if TYPE_CHECKING:
    from tracker.models import Source

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API = "https://www.strava.com/api/v3"

# Strava has ~50 sport types; goals care about a handful of buckets
SPORT_TYPES = {
    "run": {"Run", "TrailRun", "VirtualRun"},
    "ride": {"Ride", "GravelRide", "MountainBikeRide", "VirtualRide", "EBikeRide", "EMountainBikeRide", "Velomobile"},
    "swim": {"Swim"},
    "walk": {"Walk"},
    "hike": {"Hike"},
    "surf": {"Surfing", "Windsurf", "Kitesurf", "StandUpPaddling"},
    "ski": {"AlpineSki", "BackcountrySki", "NordicSki", "Snowboard"},
    "strength": {"WeightTraining", "Crossfit", "HighIntensityIntervalTraining", "Workout"},
}


def activity_type_for(sport_type: str) -> str:
    for slug, sport_types in SPORT_TYPES.items():
        if sport_type in sport_types:
            return slug
    return re.sub(r"(?<!^)(?=[A-Z])", "_", sport_type).lower()


def authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def request_token(client: httpx.Client, **params: str) -> dict:
    response = client.post(
        TOKEN_URL,
        data={"client_id": settings.STRAVA_CLIENT_ID, "client_secret": settings.STRAVA_CLIENT_SECRET, **params},
    )
    if response.status_code >= 400:
        raise SyncError(f"Strava token request failed ({response.status_code}): {response.text[:200]}")
    return response.json()


def tokens_to_secrets(tokens: dict) -> dict:
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at": tokens["expires_at"],
    }


class StravaProvider(Provider):
    kind = "strava"
    label = "Strava"
    description = "Runs, rides, swims, surf sessions and workouts. Distances in km."
    activity_types = (
        ActivityType("run", "Runs", "km", "sum"),
        ActivityType("ride", "Rides", "km", "sum"),
        ActivityType("swim", "Swims", "km", "sum"),
        ActivityType("walk", "Walks", "km", "sum"),
        ActivityType("hike", "Hikes", "km", "sum"),
        ActivityType("surf", "Surf sessions", "sessions", "count"),
        ActivityType("ski", "Ski days", "sessions", "count"),
        ActivityType("strength", "Strength workouts", "sessions", "count"),
    )
    connect_url_name = "strava_connect"
    max_pages = 20

    def default_name(self, config: dict) -> str:
        return f"Strava · {config['athlete_name']}" if config.get("athlete_name") else self.label

    def access_token(self, source: Source, client: httpx.Client) -> str:
        if source.secrets.get("expires_at", 0) > time.time() + 60:
            return source.secrets["access_token"]
        tokens = request_token(client, grant_type="refresh_token", refresh_token=source.secrets["refresh_token"])
        source.secrets = tokens_to_secrets(tokens)
        source.save(update_fields=["secrets"])
        return source.secrets["access_token"]

    def fetch(self, source: Source, client: httpx.Client, since: datetime | None) -> Iterator[FetchedActivity]:
        headers = {"Authorization": f"Bearer {self.access_token(source, client)}"}
        after = int(fetch_cutoff(since).timestamp())
        for page in range(1, self.max_pages + 1):
            response = client.get(
                f"{API}/athlete/activities",
                params={"after": after, "page": page, "per_page": 100},
                headers=headers,
            )
            response.raise_for_status()
            activities = response.json()
            for activity in activities:
                yield FetchedActivity(
                    type=activity_type_for(activity.get("sport_type") or activity["type"]),
                    external_id=str(activity["id"]),
                    occurred_at=datetime.fromisoformat(activity["start_date"]),
                    value=round(activity.get("distance", 0) / 1000, 2),
                    title=activity.get("name", ""),
                    url=f"https://www.strava.com/activities/{activity['id']}",
                )
            if len(activities) < 100:
                return
