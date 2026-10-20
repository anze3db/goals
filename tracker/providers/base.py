from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, ClassVar

import httpx
from django import forms
from django.utils import timezone

if TYPE_CHECKING:
    from datetime import date

    from tracker.models import Source


@dataclass(frozen=True)
class ActivityType:
    slug: str
    label: str
    unit: str = ""
    aggregation: str = "count"


@dataclass(frozen=True)
class FetchedActivity:
    type: str
    external_id: str
    occurred_at: datetime
    value: float = 1
    title: str = ""
    url: str = ""


class SyncError(Exception):
    pass


class WebhookError(ValueError):
    pass


class Provider:
    kind: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]
    activity_types: ClassVar[tuple[ActivityType, ...]] = ()
    config_form: ClassVar[type[forms.Form] | None] = None
    # Config form fields stored in Source.secrets instead of Source.config
    secret_fields: ClassVar[tuple[str, ...]] = ()
    # False for push-only sources, which get a webhook URL instead of a daily sync
    pulls: ClassVar[bool] = True
    # True when goals can use any activity type, not only the listed ones
    custom_types: ClassVar[bool] = False
    # Set for sources connected through OAuth instead of a config form
    connect_url_name: ClassVar[str | None] = None

    def default_name(self, config: dict) -> str:
        return self.label

    def fetch(self, source: Source, client: httpx.Client, since: datetime | None) -> Iterable[FetchedActivity]:
        raise NotImplementedError

    def parse_webhook(self, payload: object) -> list[FetchedActivity]:
        """Turn a pushed JSON or form payload into activities. Raises WebhookError for a bad payload."""
        raise NotImplementedError

    def activity_type(self, slug: str) -> ActivityType | None:
        return next((t for t in self.activity_types if t.slug == slug), None)


def start_of_year(now: datetime | None = None) -> datetime:
    now = timezone.localtime(now)
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def fetch_cutoff(since: datetime | None, overlap: timedelta = timedelta(days=7)) -> datetime:
    """Where to resume fetching: a week before the last sync (to pick up edits), or the start of the year."""
    if since is None:
        return start_of_year()
    return since - overlap


def midday(day: date) -> datetime:
    """A per-day value lands at noon local time, so it stays on its day in any nearby timezone."""
    return timezone.make_aware(datetime.combine(day, time(12)))
