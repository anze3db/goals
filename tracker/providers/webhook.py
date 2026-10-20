from datetime import date, datetime

from django.utils import timezone

from tracker.providers.base import ActivityType, FetchedActivity, Provider, WebhookError, midday

BATCH_LIMIT = 1000


def _activity(item: object) -> FetchedActivity:
    if not isinstance(item, dict):
        raise WebhookError("Each item must be an object")
    activity_type = str(item.get("type") or "event").strip().lower()[:64]
    try:
        value = float(item.get("value", 1))
    except TypeError, ValueError:
        raise WebhookError("value must be a number") from None

    day = item.get("date")
    try:
        if day:
            occurred_at = midday(date.fromisoformat(str(day)))
        elif item.get("occurred_at"):
            occurred_at = datetime.fromisoformat(str(item["occurred_at"]))
            if timezone.is_naive(occurred_at):
                occurred_at = timezone.make_aware(occurred_at)
        else:
            occurred_at = timezone.now()
    except ValueError:
        raise WebhookError("date must be YYYY-MM-DD and occurred_at ISO 8601") from None

    # A value per type per day (like steps) replaces the earlier report for that day
    external_id = str(item.get("id") or (f"{activity_type}:{day}" if day else ""))[:255]
    return FetchedActivity(
        type=activity_type,
        external_id=external_id,
        occurred_at=occurred_at,
        value=value,
        title=str(item.get("title", ""))[:500],
    )


class WebhookProvider(Provider):
    """Push-only: iOS Shortcuts (Apple Health steps, surf sessions), Home Assistant, cron jobs."""

    kind = "webhook"
    label = "Webhook"
    description = "A private URL anything can POST to. Use it with iOS Shortcuts for Apple Health."
    activity_types = (
        ActivityType("steps", "Steps", "steps", "sum"),
        ActivityType("surf", "Surf sessions", "sessions", "count"),
        ActivityType("workout", "Workouts", "sessions", "count"),
    )
    pulls = False
    custom_types = True

    def parse_webhook(self, payload: object) -> list[FetchedActivity]:
        items = payload if isinstance(payload, list) else [payload]
        if len(items) > BATCH_LIMIT:
            raise WebhookError(f"At most {BATCH_LIMIT} items per request")
        return [_activity(item) for item in items]
