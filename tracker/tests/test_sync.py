from datetime import UTC, datetime
from unittest import mock

import httpx
from django.test import TestCase
from model_bakery import baker
from potatoq import current_app
from potatoq.testing import due

from tracker.models import Activity, Source
from tracker.providers import FetchedActivity
from tracker.sync import store_activities, sync_source
from tracker.tasks import sync_all_sources, sync_source_task

RSS = b"""<rss><channel>
<item><title>One</title><link>https://b/1</link><guid>1</guid><pubDate>Mon, 08 Jun 2026 01:15:00 +0000</pubDate></item>
</channel></rss>"""

WHEN = datetime(2026, 6, 8, tzinfo=UTC)


def feed_client(content: bytes = RSS, status: int = 200) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=content)))


class StoreActivitiesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = baker.make(Source, kind="webhook")

    def test_inserts_then_updates_by_external_id(self):
        created = store_activities(
            self.source,
            [
                FetchedActivity("steps", "steps:2026-06-08", WHEN, value=100),
                FetchedActivity("event", "", WHEN),
                FetchedActivity("event", "", WHEN),
            ],
        )
        self.assertEqual(created, 3)

        created = store_activities(self.source, [FetchedActivity("steps", "steps:2026-06-08", WHEN, value=250, title="Later")])
        self.assertEqual(created, 0)
        steps = Activity.objects.get(external_id="steps:2026-06-08")
        self.assertEqual(steps.value, 250)
        self.assertEqual(steps.title, "Later")
        self.assertEqual(steps.user_id, self.source.user_id)
        self.assertEqual(Activity.objects.count(), 3)

    def test_last_duplicate_in_a_batch_wins(self):
        store_activities(self.source, [FetchedActivity("steps", "a", WHEN, value=1), FetchedActivity("steps", "a", WHEN, value=2)])
        self.assertEqual(Activity.objects.get(external_id="a").value, 2)

    def test_truncates_long_titles(self):
        store_activities(self.source, [FetchedActivity("post", "x", WHEN, title="t" * 600)])
        self.assertEqual(len(Activity.objects.get(external_id="x").title), 500)


class SyncSourceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = baker.make(Source, kind="feed", config={"feed_url": "https://b/feed.xml"}, last_error="old")

    def test_success(self):
        self.assertEqual(sync_source(self.source, feed_client()), 1)
        self.assertEqual(sync_source(self.source, feed_client()), 0)
        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_synced_at)
        self.assertEqual(self.source.last_error, "")
        self.assertEqual(self.source.activities.get().title, "One")

    def test_failure_is_recorded_not_raised(self):
        with self.assertLogs("tracker.sync", level="ERROR"):
            self.assertEqual(sync_source(self.source, feed_client(status=503)), 0)
        self.source.refresh_from_db()
        self.assertIn("HTTPStatusError", self.source.last_error)
        self.assertIsNone(self.source.last_synced_at)

    def test_push_only_sources_are_skipped(self):
        self.assertEqual(sync_source(baker.make(Source, kind="webhook")), 0)


class TasksTest(TestCase):
    def test_sync_all_fans_out_to_enabled_pull_sources(self):
        feed = baker.make(Source, kind="feed", config={"feed_url": "https://b/feed.xml"})
        baker.make(Source, kind="feed", enabled=False)
        baker.make(Source, kind="webhook")
        with mock.patch("tracker.sync.make_client", side_effect=lambda: feed_client()):
            self.assertEqual(sync_all_sources.delay().get(), 1)
        self.assertEqual(feed.activities.count(), 1)

    def test_sources_sync_once_a_day_at_five(self):
        runs = due(current_app(), datetime(2026, 1, 1), datetime(2026, 1, 3))
        self.assertEqual(
            [(name, run.day, run.hour, run.minute) for name, run in runs], [("sync-sources", 1, 5, 0), ("sync-sources", 2, 5, 0)]
        )

    def test_missing_source(self):
        self.assertEqual(sync_source_task.delay(123456).get(), 0)
