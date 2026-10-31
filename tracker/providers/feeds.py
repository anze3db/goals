from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING
from xml.etree import ElementTree

import httpx
from django import forms
from django.utils import timezone

from tracker.providers.base import ActivityType, FetchedActivity, Provider, SyncError

if TYPE_CHECKING:
    from tracker.models import Source

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _text(element: ElementTree.Element, tag: str) -> str:
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(content: bytes) -> Iterator[dict]:
    """Yield entries from an RSS 2.0 or Atom feed as dicts of raw strings."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as e:
        raise SyncError(f"Not a valid feed: {e}") from e

    for item in root.iter("item"):
        yield {child.tag: (child.text or "").strip() for child in item}

    for entry in root.iter(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link")
        yield {
            "guid": _text(entry, f"{ATOM}id"),
            "title": _text(entry, f"{ATOM}title"),
            "link": link.get("href", "") if link is not None else "",
            "pubDate": _text(entry, f"{ATOM}published") or _text(entry, f"{ATOM}updated"),
        }


def get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response


class FeedForm(forms.Form):
    feed_url = forms.URLField(label="Feed URL", help_text="RSS or Atom, e.g. https://blog.pecar.me/feed.xml")


class FeedProvider(Provider):
    kind = "feed"
    label = "RSS / Atom feed"
    description = "Counts new entries in a blog or any other feed."
    activity_types = (ActivityType("post", "Posts", "posts", "count"),)
    config_form = FeedForm

    def default_name(self, config: dict) -> str:
        return httpx.URL(config["feed_url"]).host or self.label

    def fetch(self, source: Source, client: httpx.Client, since: datetime | None) -> Iterator[FetchedActivity]:
        response = get(client, source.config["feed_url"])
        for entry in parse_feed(response.content):
            occurred_at = parse_date(entry.get("pubDate"))
            external_id = entry.get("guid") or entry.get("link")
            if occurred_at is None or not external_id:
                continue
            yield FetchedActivity(
                type="post",
                external_id=external_id,
                occurred_at=occurred_at,
                title=entry.get("title", ""),
                url=entry.get("link", ""),
            )
