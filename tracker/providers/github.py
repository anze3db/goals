from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
from django import forms
from django.utils import timezone

from tracker.providers.base import ActivityType, FetchedActivity, Provider, SyncError, midday, start_of_year

if TYPE_CHECKING:
    from tracker.models import Source

API = "https://api.github.com"

CONTRIBUTIONS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


class GitHubForm(forms.Form):
    username = forms.CharField(label="GitHub username")
    token = forms.CharField(
        label="Personal access token",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Read-only, no scopes needed. Required for daily contributions; without it only releases are tracked.",
    )


class GitHubProvider(Provider):
    kind = "github"
    label = "GitHub"
    description = "Releases on your repositories and your daily contribution count."
    activity_types = (
        ActivityType("release", "Releases", "releases", "count"),
        ActivityType("contribution", "Contributions", "contributions", "sum"),
    )
    config_form = GitHubForm
    secret_fields = ("token",)
    max_pages = 10

    def default_name(self, config: dict) -> str:
        return f"GitHub · {config['username']}"

    def _headers(self, source: Source) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token := source.secrets.get("token"):
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def fetch(self, source: Source, client: httpx.Client, since: datetime | None) -> Iterator[FetchedActivity]:
        headers = self._headers(source)
        yield from self._releases(source, client, headers, since)
        if source.secrets.get("token"):
            yield from self._contributions(source, client, headers)

    def _repositories(self, source: Source, client: httpx.Client, headers: dict) -> Iterator[dict]:
        for page in range(1, self.max_pages + 1):
            response = client.get(
                f"{API}/users/{source.config['username']}/repos",
                params={"type": "owner", "per_page": 100, "page": page},
                headers=headers,
            )
            response.raise_for_status()
            repos = response.json()
            yield from repos
            if len(repos) < 100:
                return

    def _releases(self, source: Source, client: httpx.Client, headers: dict, since: datetime | None) -> Iterator[FetchedActivity]:
        for repo in self._repositories(source, client, headers):
            if repo["fork"]:
                continue
            # A release pushes a tag, so repos untouched since the last sync can't have new ones
            if since and datetime.fromisoformat(repo["pushed_at"]) < since - timedelta(days=1):
                continue
            response = client.get(f"{API}/repos/{repo['full_name']}/releases", params={"per_page": 100}, headers=headers)
            response.raise_for_status()
            for release in response.json():
                if release["draft"] or not release["published_at"]:
                    continue
                yield FetchedActivity(
                    type="release",
                    external_id=f"release:{release['id']}",
                    occurred_at=datetime.fromisoformat(release["published_at"]),
                    title=f"{repo['name']} {release['tag_name']}",
                    url=release["html_url"],
                )

    def _contributions(self, source: Source, client: httpx.Client, headers: dict) -> Iterator[FetchedActivity]:
        response = client.post(
            f"{API}/graphql",
            json={
                "query": CONTRIBUTIONS_QUERY,
                "variables": {
                    "login": source.config["username"],
                    "from": start_of_year().isoformat(),
                    "to": timezone.now().isoformat(),
                },
            },
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise SyncError(payload["errors"][0].get("message", "GitHub GraphQL error"))
        weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                if not day["contributionCount"]:
                    continue
                yield FetchedActivity(
                    type="contribution",
                    external_id=f"contribution:{day['date']}",
                    occurred_at=midday(date.fromisoformat(day["date"])),
                    value=day["contributionCount"],
                    title=f"{day['contributionCount']} contributions",
                )
