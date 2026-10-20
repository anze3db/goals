from datetime import date, datetime

from django.utils import timezone
from django.utils.text import Truncator

from tracker.providers.base import ActivityType, FetchedActivity, Provider, WebhookError, midday

MAX_POSTS = 1000
ENGAGEMENT_FIELDS = ("likes", "reposts", "replies", "quotes")


def _count(item: dict, field: str) -> int:
    value = item.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebhookError(f"{field} must be a whole number")
    return value


def _post_activities(post: object) -> list[FetchedActivity]:
    if not isinstance(post, dict) or not post.get("id"):
        raise WebhookError("Each post must be an object with an id")
    try:
        created_at = datetime.fromisoformat(str(post["created_at"]))
    except KeyError, ValueError:
        raise WebhookError("Each post needs an ISO 8601 created_at") from None
    if timezone.is_naive(created_at):
        created_at = timezone.make_aware(created_at)

    post_id = str(post["id"])[:200]
    title = Truncator(str(post.get("text", ""))).chars(80)
    url = str(post.get("url", ""))
    # Engagement and views keep growing for a few days, so each delivery updates the earlier numbers
    return [
        FetchedActivity(type="post", external_id=f"post:{post_id}", occurred_at=created_at, title=title, url=url),
        FetchedActivity(
            type="engagement",
            external_id=f"engagement:{post_id}",
            occurred_at=created_at,
            value=sum(_count(post, field) for field in ENGAGEMENT_FIELDS),
            title=title,
            url=url,
        ),
        FetchedActivity(
            type="views", external_id=f"views:{post_id}", occurred_at=created_at, value=_count(post, "views"), title=title, url=url
        ),
    ]


class XProvider(Provider):
    """Push-only: a daily job that scrapes the X profile and POSTs its numbers and recent posts."""

    kind = "x"
    label = "X (Twitter)"
    description = "A daily push of your follower count and recent posts with their likes, reposts, replies and views."
    activity_types = (
        ActivityType("post", "Posts", "posts", "count"),
        ActivityType("engagement", "Likes, reposts, replies and quotes", "interactions", "sum"),
        ActivityType("views", "Post views", "views", "sum"),
        ActivityType("followers", "Followers", "followers", "latest"),
    )
    pulls = False

    def parse_webhook(self, payload: object) -> list[FetchedActivity]:
        if not isinstance(payload, dict):
            raise WebhookError("Send one JSON object per day")
        try:
            day = date.fromisoformat(str(payload["date"]))
        except KeyError, ValueError:
            raise WebhookError("date must be YYYY-MM-DD") from None
        posts = payload.get("posts", [])
        if not isinstance(posts, list):
            raise WebhookError("posts must be a list")
        if len(posts) > MAX_POSTS:
            raise WebhookError(f"At most {MAX_POSTS} posts per request")

        if "followers" not in payload:
            raise WebhookError("followers is required")
        followers = _count(payload, "followers")
        fetched = [
            FetchedActivity(
                type="followers",
                external_id=f"followers:{day.isoformat()}",
                occurred_at=midday(day),
                value=followers,
                title=f"{followers} followers",
            )
        ]
        for post in posts:
            fetched.extend(_post_activities(post))
        return fetched
