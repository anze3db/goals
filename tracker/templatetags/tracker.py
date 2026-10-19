from datetime import datetime

from django import template
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone

from tracker.models import SyncRun
from tracker.progress import format_number

register = template.Library()


@register.filter
def ago(value: datetime | None) -> str:
    """naturaltime, except daily totals stamped later today read as "today" instead of "in 10 hours"."""
    if value is None:
        return ""
    if value > timezone.now():
        return "today"
    return naturaltime(value)


@register.filter
def sync_summary(run: SyncRun) -> str:
    """What a sync brought back per activity type, e.g. "Contributions: 1,234 across 210 entries · Releases: 12"."""
    parts = []
    for slug, entry in sorted(run.summary.items()):
        kind = run.source.provider.activity_type(slug)
        label = kind.label if kind else slug
        if kind and kind.aggregation == "count":
            parts.append(f"{label}: {format_number(entry['count'])}")
        else:
            parts.append(f"{label}: {format_number(entry['total'])} across {format_number(entry['count'])} entries")
    return " · ".join(parts)
