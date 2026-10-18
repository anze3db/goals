import logging
from collections.abc import Iterable

import httpx
from django.db import transaction
from django.utils import timezone

from tracker.models import Activity, Source
from tracker.providers import FetchedActivity

logger = logging.getLogger(__name__)

_FIELD_NAMES = ("type", "value", "occurred_at", "title", "url")


def make_client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "goals.pecar.me (+https://goals.pecar.me)"})


def _fields(item: FetchedActivity) -> dict:
    return {
        "type": item.type,
        "value": item.value,
        "occurred_at": item.occurred_at,
        "title": item.title[:500],
        "url": item.url[:1000],
    }


@transaction.atomic
def store_activities(source: Source, fetched: Iterable[FetchedActivity]) -> int:
    """Insert new activities and update changed ones (matched on external_id). Returns how many were new."""
    keyed: dict[str, FetchedActivity] = {}
    anonymous: list[FetchedActivity] = []
    for item in fetched:
        if item.external_id:
            keyed[item.external_id] = item
        else:
            anonymous.append(item)

    existing = {a.external_id: a for a in Activity.objects.filter(source=source, external_id__in=list(keyed))}
    new_items = [*anonymous, *(item for key, item in keyed.items() if key not in existing)]
    to_create = [Activity(user_id=source.user_id, source=source, external_id=item.external_id, **_fields(item)) for item in new_items]
    to_update = []
    for key, activity in existing.items():
        fields = _fields(keyed[key])
        if any(getattr(activity, name) != value for name, value in fields.items()):
            for name, value in fields.items():
                setattr(activity, name, value)
            to_update.append(activity)

    Activity.objects.bulk_create(to_create, batch_size=500)
    Activity.objects.bulk_update(to_update, list(_FIELD_NAMES), batch_size=500)
    return len(to_create)


def sync_source(source: Source, client: httpx.Client | None = None) -> int:
    """Pull new activities for a source and record how it went. Never raises for a failing service."""
    provider = source.provider
    if not provider.pulls:
        return 0

    started_at = timezone.now()
    client = client or make_client()
    try:
        with client:
            fetched = list(provider.fetch(source, client, since=source.last_synced_at))
    except Exception as e:  # A broken integration must not take down the others or dead-letter the task
        logger.exception("Syncing source %s (%s) failed", source.pk, source.kind)
        source.last_error = f"{type(e).__name__}: {e}"[:2000]
        source.save(update_fields=["last_error"])
        return 0

    created = store_activities(source, fetched)
    source.last_synced_at = started_at
    source.last_error = ""
    source.save(update_fields=["last_synced_at", "last_error"])
    return created
