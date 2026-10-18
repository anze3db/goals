from datetime import datetime

from django import template
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone

register = template.Library()


@register.filter
def ago(value: datetime | None) -> str:
    """naturaltime, except daily totals stamped later today read as "today" instead of "in 10 hours"."""
    if value is None:
        return ""
    if value > timezone.now():
        return "today"
    return naturaltime(value)
