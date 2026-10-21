import json
import secrets
from collections.abc import Sequence
from datetime import datetime

from django.db import models
from django.http import HttpRequest
from django.utils import timezone

from tracker.providers import FetchedActivity, Provider, get_provider
from users.models import User


def _new_webhook_token() -> str:
    return secrets.token_urlsafe(24)


def _current_year() -> int:
    return timezone.localdate().year


class Source(models.Model):
    """A connected service (Strava, GitHub, a feed, a webhook, ...) that produces activities."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sources")
    kind = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)
    secrets = models.JSONField(default=dict, blank=True)
    webhook_token = models.CharField(max_length=64, unique=True, default=_new_webhook_token)
    enabled = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_created"]

    def __str__(self) -> str:
        return self.name

    @property
    def provider(self) -> Provider:
        return get_provider(self.kind)


class Goal(models.Model):
    class Aggregation(models.TextChoices):
        SUM = "sum", "Add up the values"
        COUNT = "count", "Count the activities"
        LATEST = "latest", "Latest value (e.g. followers)"

    class Period(models.TextChoices):
        YEAR = "year", "Per year"
        MONTH = "month", "Per month"
        WEEK = "week", "Per week"
        DAY = "day", "Per day"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tracked_goals")
    name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(default=_current_year)
    target = models.FloatField()
    unit = models.CharField(max_length=32, blank=True)
    # Without a source the goal is logged by hand
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True, related_name="goals")
    activity_type = models.CharField(max_length=64, blank=True)
    aggregation = models.CharField(max_length=16, choices=Aggregation.choices, default=Aggregation.SUM)
    # The target applies to each period: 10,000 steps per day, 3 workouts per week, 1,000 km per year
    period = models.CharField(max_length=8, choices=Period.choices, default=Period.YEAR)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date_created"]
        indexes = [models.Index(fields=["user", "year"])]

    def __str__(self) -> str:
        return self.name

    @property
    def is_manual(self) -> bool:
        return self.source_id is None

    def activities(self) -> models.QuerySet[Activity]:
        if self.source_id is None:
            if self.pk is None:
                # A goal being previewed before it's saved has nothing logged yet
                return Activity.objects.none()
            qs = Activity.objects.filter(goal=self)
        else:
            qs = Activity.objects.filter(source_id=self.source_id, type=self.activity_type)
        return qs.filter(occurred_at__year=self.year)


class Activity(models.Model):
    """One thing that happened: a run, a release, a post, a day's step count, a manual log."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activities")
    source = models.ForeignKey(Source, on_delete=models.CASCADE, null=True, blank=True, related_name="activities")
    # Only set for activities logged by hand on a goal without a source
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, null=True, blank=True, related_name="manual_activities")
    type = models.CharField(max_length=64)
    value = models.FloatField(default=1)
    occurred_at = models.DateTimeField()
    # The source's own id, so re-syncing updates instead of duplicating
    external_id = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=500, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["source", "type", "occurred_at"]),
            models.Index(fields=["user", "-occurred_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~models.Q(external_id=""),
                name="unique_external_id_per_source",
            )
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.value} @ {self.occurred_at:%Y-%m-%d}"


class WebhookDelivery(models.Model):
    """A request that reached a webhook URL and what we answered, so Shortcuts and friends can be debugged."""

    KEEP_PER_SOURCE = 50
    MAX_BODY_LENGTH = 20_000

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="deliveries")
    received_at = models.DateTimeField(auto_now_add=True)
    content_type = models.CharField(max_length=255, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    status_code = models.PositiveSmallIntegerField()
    response = models.JSONField(default=dict)

    class Meta:
        ordering = ["-received_at", "-pk"]
        verbose_name_plural = "webhook deliveries"

    def __str__(self) -> str:
        return f"{self.status_code} @ {self.received_at:%Y-%m-%d %H:%M}"

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    @property
    def pretty_body(self) -> str:
        try:
            return json.dumps(json.loads(self.body), indent=2, ensure_ascii=False)
        except ValueError:
            return self.body

    @property
    def pretty_response(self) -> str:
        return json.dumps(self.response, indent=2, ensure_ascii=False)

    @classmethod
    def record(cls, source: Source, request: HttpRequest, body: bytes, status_code: int, response: dict) -> WebhookDelivery:
        delivery = cls.objects.create(
            source=source,
            content_type=request.content_type or "",
            user_agent=request.headers.get("User-Agent", "")[:255],
            body=body.decode("utf-8", errors="replace")[: cls.MAX_BODY_LENGTH],
            status_code=status_code,
            response=response,
        )
        stale = cls.objects.filter(source=source).values_list("pk", flat=True)[cls.KEEP_PER_SOURCE :]
        cls.objects.filter(pk__in=list(stale)).delete()
        return delivery


class SyncRun(models.Model):
    """One pull from a source's service and how it went, so a failing or suspiciously empty sync can be spotted."""

    KEEP_PER_SOURCE = 50

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="sync_runs")
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    fetched = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    # {activity type: {"count": n, "total": sum of values}} for what came back
    summary = models.JSONField(default=dict)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "-pk"]

    def __str__(self) -> str:
        return f"{'ok' if self.ok else 'failed'} @ {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @classmethod
    def record(
        cls, source: Source, started_at: datetime, fetched: Sequence[FetchedActivity] = (), created: int = 0, error: str = ""
    ) -> SyncRun:
        summary: dict[str, dict[str, float]] = {}
        for item in fetched:
            entry = summary.setdefault(item.type, {"count": 0, "total": 0})
            entry["count"] += 1
            entry["total"] += item.value
        run = cls.objects.create(
            source=source,
            started_at=started_at,
            finished_at=timezone.now(),
            fetched=len(fetched),
            created=created,
            summary=summary,
            error=error,
        )
        stale = cls.objects.filter(source=source).values_list("pk", flat=True)[cls.KEEP_PER_SOURCE :]
        cls.objects.filter(pk__in=list(stale)).delete()
        return run
