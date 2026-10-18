import xmlrpc.client
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, cast

import httpx
from django import forms

from tracker.providers.base import ActivityType, FetchedActivity, Provider

if TYPE_CHECKING:
    from tracker.models import Source


class PyPIForm(forms.Form):
    username = forms.CharField(label="PyPI username", required=False, help_text="Tracks every package you own or maintain.")
    packages = forms.CharField(
        label="Extra packages",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One per line, for packages you release but don't own.",
    )

    def clean(self):
        cleaned = super().clean()
        cleaned["packages"] = [p.strip() for p in cleaned.get("packages", "").split() if p.strip()]
        if not cleaned.get("username") and not cleaned["packages"]:
            raise forms.ValidationError("Enter a username or at least one package")
        return cleaned


class PyPIProvider(Provider):
    kind = "pypi"
    label = "PyPI"
    description = "New versions of your Python packages."
    activity_types = (ActivityType("release", "Releases", "releases", "count"),)
    config_form = PyPIForm

    def default_name(self, config: dict) -> str:
        return f"PyPI · {config['username']}" if config.get("username") else self.label

    def _user_packages(self, client: httpx.Client, username: str) -> list[str]:
        # PyPI has no JSON endpoint for this; the XML-RPC one still works
        response = client.post(
            "https://pypi.org/pypi",
            content=xmlrpc.client.dumps((username,), "user_packages"),
            headers={"Content-Type": "text/xml"},
        )
        response.raise_for_status()
        params, _ = xmlrpc.client.loads(response.content)
        roles = cast(list[list[str]], params[0])
        return [name for _role, name in roles]

    def fetch(self, source: Source, client: httpx.Client, since: datetime | None) -> Iterator[FetchedActivity]:
        packages = set(source.config.get("packages", []))
        if username := source.config.get("username"):
            packages.update(self._user_packages(client, username))

        for package in sorted(packages):
            response = client.get(f"https://pypi.org/pypi/{package}/json")
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()
            name = data["info"]["name"]
            for version, files in data["releases"].items():
                if not files:
                    continue
                yield FetchedActivity(
                    type="release",
                    external_id=f"{name}=={version}",
                    occurred_at=min(datetime.fromisoformat(f["upload_time_iso_8601"]) for f in files),
                    title=f"{name} {version}",
                    url=f"https://pypi.org/project/{name}/{version}/",
                )
