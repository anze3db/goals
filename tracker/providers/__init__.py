from tracker.providers.base import ActivityType, FetchedActivity, Provider, SyncError
from tracker.providers.feeds import FeedProvider, GoodreadsProvider
from tracker.providers.github import GitHubProvider
from tracker.providers.mastodon import MastodonProvider
from tracker.providers.pypi import PyPIProvider
from tracker.providers.strava import StravaProvider
from tracker.providers.webhook import WebhookProvider

PROVIDERS: dict[str, Provider] = {
    provider.kind: provider
    for provider in (
        StravaProvider(),
        GitHubProvider(),
        PyPIProvider(),
        FeedProvider(),
        GoodreadsProvider(),
        MastodonProvider(),
        WebhookProvider(),
    )
}


def get_provider(kind: str) -> Provider:
    return PROVIDERS[kind]


__all__ = ["PROVIDERS", "ActivityType", "FetchedActivity", "Provider", "SyncError", "get_provider"]
