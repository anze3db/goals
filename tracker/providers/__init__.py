from tracker.providers.base import ActivityType, FetchedActivity, Provider, SyncError, WebhookError
from tracker.providers.feeds import FeedProvider, GoodreadsProvider
from tracker.providers.github import GitHubProvider
from tracker.providers.mastodon import MastodonProvider
from tracker.providers.pypi import PyPIProvider
from tracker.providers.strava import StravaProvider
from tracker.providers.webhook import WebhookProvider
from tracker.providers.x import XProvider

PROVIDERS: dict[str, Provider] = {
    provider.kind: provider
    for provider in (
        StravaProvider(),
        GitHubProvider(),
        PyPIProvider(),
        FeedProvider(),
        GoodreadsProvider(),
        MastodonProvider(),
        XProvider(),
        WebhookProvider(),
    )
}


def get_provider(kind: str) -> Provider:
    return PROVIDERS[kind]


__all__ = ["PROVIDERS", "ActivityType", "FetchedActivity", "Provider", "SyncError", "WebhookError", "get_provider"]
