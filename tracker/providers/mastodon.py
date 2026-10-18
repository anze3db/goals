import re
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
from django import forms
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import Truncator

from tracker.providers.base import ActivityType, FetchedActivity, Provider, fetch_cutoff, midday

if TYPE_CHECKING:
    from tracker.models import Source

HANDLE_RE = re.compile(r"^@?(?P<user>[\w.-]+)@(?P<instance>[\w.-]+\.[a-z]{2,})$", re.IGNORECASE)
PROFILE_URL_RE = re.compile(r"^https?://(?P<instance>[\w.-]+)/@(?P<user>[\w.-]+)/?$", re.IGNORECASE)


class MastodonForm(forms.Form):
    handle = forms.CharField(label="Mastodon handle", help_text="@you@instance.social or your profile URL")

    def clean_handle(self) -> str:
        value = self.cleaned_data["handle"].strip()
        match = HANDLE_RE.match(value) or PROFILE_URL_RE.match(value)
        if not match:
            raise forms.ValidationError("Use the form @you@instance.social")
        return f"@{match['user']}@{match['instance'].lower()}"


class MastodonProvider(Provider):
    kind = "mastodon"
    label = "Mastodon"
    description = "Posts, the likes/boosts/replies they get, and a daily follower count. Public data only."
    activity_types = (
        ActivityType("post", "Posts", "posts", "count"),
        ActivityType("engagement", "Likes, boosts and replies", "interactions", "sum"),
        ActivityType("followers", "Followers", "followers", "latest"),
    )
    config_form = MastodonForm
    max_pages = 50

    def default_name(self, config: dict) -> str:
        return config["handle"]

    def fetch(self, source: Source, client: httpx.Client, since: datetime | None) -> Iterator[FetchedActivity]:
        _, user, instance = source.config["handle"].split("@")
        api = f"https://{instance}/api/v1"

        response = client.get(f"{api}/accounts/lookup", params={"acct": user})
        response.raise_for_status()
        account = response.json()

        today = timezone.localdate()
        yield FetchedActivity(
            type="followers",
            external_id=f"followers:{today.isoformat()}",
            occurred_at=midday(today),
            value=account["followers_count"],
            title=f"{account['followers_count']} followers",
        )

        # Re-read the last week of posts on every sync so engagement counts stay fresh
        cutoff = fetch_cutoff(since)
        params: dict[str, str | int] = {"limit": 40, "exclude_reblogs": "true"}
        for _ in range(self.max_pages):
            response = client.get(f"{api}/accounts/{account['id']}/statuses", params=params)
            response.raise_for_status()
            statuses = response.json()
            if not statuses:
                return
            for status in statuses:
                created_at = datetime.fromisoformat(status["created_at"])
                if created_at < cutoff:
                    if status.get("pinned"):
                        continue
                    return
                title = Truncator(strip_tags(status["content"])).chars(80)
                yield FetchedActivity(
                    type="post",
                    external_id=f"post:{status['id']}",
                    occurred_at=created_at,
                    title=title,
                    url=status["url"] or "",
                )
                yield FetchedActivity(
                    type="engagement",
                    external_id=f"engagement:{status['id']}",
                    occurred_at=created_at,
                    value=status["favourites_count"] + status["reblogs_count"] + status["replies_count"],
                    title=title,
                    url=status["url"] or "",
                )
            params["max_id"] = statuses[-1]["id"]
