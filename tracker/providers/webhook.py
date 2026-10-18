from tracker.providers.base import ActivityType, Provider


class WebhookProvider(Provider):
    """Push-only: iOS Shortcuts (Apple Health steps, surf sessions), Home Assistant, cron jobs."""

    kind = "webhook"
    label = "Webhook"
    description = "A private URL anything can POST to. Use it with iOS Shortcuts for Apple Health."
    activity_types = (
        ActivityType("steps", "Steps", "steps", "sum"),
        ActivityType("surf", "Surf sessions", "sessions", "count"),
        ActivityType("workout", "Workouts", "sessions", "count"),
    )
    pulls = False
    custom_types = True
