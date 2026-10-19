import json
from datetime import timedelta
from typing import ClassVar
from unittest import mock

import httpx
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from tracker.models import Activity, Goal, Source
from tracker.providers import SyncError
from users.models import User

RSS = b"""<rss><channel>
<item><title>Hello</title><link>https://b/1</link><guid>1</guid><pubDate>Mon, 08 Jun 2026 01:15:00 +0000</pubDate></item>
</channel></rss>"""


def feed_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=RSS)))


class TrackerViewTestCase(TestCase):
    user: ClassVar[User]
    other: ClassVar[User]
    year: ClassVar[int]
    strava: ClassVar[Source]
    feed: ClassVar[Source]
    hook: ClassVar[Source]
    run_goal: ClassVar[Goal]
    posts_goal: ClassVar[Goal]
    manual_goal: ClassVar[Goal]

    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(User, username="anze", first_name="Anže")
        cls.other = baker.make(User, username="other")
        cls.year = timezone.localdate().year
        cls.strava = baker.make(Source, user=cls.user, kind="strava", name="Strava · Anže", last_synced_at=timezone.now())
        cls.feed = baker.make(
            Source,
            user=cls.user,
            kind="feed",
            name="blog.pecar.me",
            config={"feed_url": "https://blog.pecar.me/feed.xml"},
            last_error="HTTPStatusError: 503",
        )
        cls.hook = baker.make(Source, user=cls.user, kind="webhook", name="Apple Health")
        cls.run_goal = baker.make(
            Goal, user=cls.user, name="Run 1,000 km", year=cls.year, target=1000, unit="km", source=cls.strava, activity_type="run"
        )
        cls.posts_goal = baker.make(
            Goal,
            user=cls.user,
            name="Publish 12 posts",
            year=cls.year,
            target=12,
            unit="posts",
            source=cls.feed,
            activity_type="post",
            aggregation=Goal.Aggregation.COUNT,
        )
        cls.manual_goal = baker.make(Goal, user=cls.user, name="Dinners with friends", year=cls.year, target=52, unit="dinners")
        now = timezone.now()
        for days, km in [(1, 10.5), (3, 21.1), (40, 8)]:
            baker.make(
                Activity,
                user=cls.user,
                source=cls.strava,
                type="run",
                value=km,
                occurred_at=now - timedelta(days=days),
                title="Morning run",
                external_id=f"run-{days}",
            )
        baker.make(
            Activity, user=cls.user, source=cls.feed, type="post", occurred_at=now - timedelta(days=2), title="A post", external_id="p1"
        )
        baker.make(Activity, user=cls.user, goal=cls.manual_goal, type="manual", occurred_at=now - timedelta(days=5))

    def setUp(self):
        self.client.force_login(self.user)


class DashboardTest(TrackerViewTestCase):
    def test_anonymous_sees_landing(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertContains(response, "Goals that track themselves")
        self.assertContains(response, reverse("login"))

    def test_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Run 1,000 km")
        self.assertContains(response, "<strong>39.6</strong>", html=True)
        self.assertContains(response, "Dinners with friends")
        self.assertContains(response, reverse("goal_log", args=[self.manual_goal.pk]))
        self.assertContains(response, "1 source failing")
        self.assertContains(response, "Morning run")
        self.assertContains(response, 'class="chart ')
        self.assertContains(response, "One tracked by hand.")

    def test_other_year_is_empty(self):
        response = self.client.get("/?year=1999")
        self.assertContains(response, "No goals for 1999 yet")
        self.assertContains(response, "1999 · final")

    def test_query_count_is_bounded(self):
        with self.assertNumQueries(9):
            self.client.get("/")


class YearViewTest(TrackerViewTestCase):
    def test_squares(self):
        response = self.client.get(reverse("year"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Publish 12 posts")
        self.assertContains(response, "day streak")
        self.assertContains(response, "c l4")
        self.assertContains(response, "today")


class ReportTest(TrackerViewTestCase):
    def test_owner_sees_private_report(self):
        response = self.client.get(reverse("report", args=["anze", self.year]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anže's year so far")
        self.assertContains(response, "Run 1,000 km, month by month")
        self.assertContains(response, "Biggest single: 21.1 km")
        self.assertContains(response, "Back to the app")

    def test_private_report_is_hidden(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("report", args=["anze", self.year])).status_code, 404)

    def test_public_report(self):
        User.objects.filter(pk=self.user.pk).update(public_report=True)
        self.client.logout()
        response = self.client.get(reverse("report", args=["anze", self.year]))
        self.assertContains(response, "Sources: RSS / Atom feed, Strava")
        self.assertNotContains(response, "Back to the app")

    def test_my_report_redirects(self):
        response = self.client.get(reverse("my_report") + "?year=2025")
        self.assertRedirects(response, reverse("report", args=["anze", 2025]))


class GoalViewsTest(TrackerViewTestCase):
    def test_new_goal_form_lists_metrics(self):
        response = self.client.get(reverse("goal_new"))
        self.assertContains(response, f'value="{self.strava.pk}:surf"')
        self.assertContains(response, f'value="{self.hook.pk}:custom"')
        self.assertContains(response, 'value="manual"')

    def test_create_with_metric_defaults(self):
        response = self.client.post(
            reverse("goal_new"),
            {"name": "Surf", "target": 30, "unit": "", "year": self.year, "metric": f"{self.strava.pk}:surf", "aggregation": ""},
        )
        self.assertRedirects(response, f"/?year={self.year}")
        goal = Goal.objects.get(name="Surf")
        self.assertEqual((goal.source, goal.activity_type, goal.aggregation, goal.unit), (self.strava, "surf", "count", "sessions"))

    def test_create_custom_webhook_type(self):
        data = {"name": "Swims", "target": 10, "year": self.year, "metric": f"{self.hook.pk}:custom"}
        response = self.client.post(reverse("goal_new"), data)
        self.assertContains(response, "Enter the activity type your webhook sends")
        self.client.post(reverse("goal_new"), data | {"custom_type": "pool-swim", "aggregation": "count"})
        goal = Goal.objects.get(name="Swims")
        self.assertEqual((goal.activity_type, goal.aggregation), ("pool-swim", "count"))

    def test_cannot_use_someone_elses_source(self):
        foreign = baker.make(Source, user=self.other, kind="feed")
        response = self.client.post(reverse("goal_new"), {"name": "X", "target": 1, "year": self.year, "metric": f"{foreign.pk}:post"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Goal.objects.filter(name="X").exists())

    def test_edit_and_delete(self):
        response = self.client.get(reverse("goal_edit", args=[self.posts_goal.pk]))
        self.assertContains(response, "Delete goal")
        self.client.post(
            reverse("goal_edit", args=[self.posts_goal.pk]),
            {"name": "Publish 20 posts", "target": 20, "unit": "posts", "year": self.year, "metric": "manual", "aggregation": "count"},
        )
        self.posts_goal.refresh_from_db()
        self.assertEqual((self.posts_goal.name, self.posts_goal.source), ("Publish 20 posts", None))

        self.client.post(reverse("goal_delete", args=[self.posts_goal.pk]))
        self.assertFalse(Goal.objects.filter(pk=self.posts_goal.pk).exists())

    def test_other_users_goal(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("goal_edit", args=[self.run_goal.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("goal_delete", args=[self.run_goal.pk])).status_code, 404)

    def test_log_manual_goal(self):
        response = self.client.post(reverse("goal_log", args=[self.manual_goal.pk]), {"amount": "2", "note": "Pizza"})
        self.assertRedirects(response, f"/?year={self.year}")
        logged = self.manual_goal.manual_activities.get(title="Pizza")
        self.assertEqual(logged.value, 2)

    def test_log_rejects_bad_input_and_automatic_goals(self):
        self.client.post(reverse("goal_log", args=[self.manual_goal.pk]), {"amount": "lots"})
        self.assertEqual(self.manual_goal.manual_activities.count(), 1)
        self.assertEqual(self.client.post(reverse("goal_log", args=[self.run_goal.pk]), {"amount": 1}).status_code, 404)


class SourceViewsTest(TrackerViewTestCase):
    def test_sources_page(self):
        response = self.client.get(reverse("sources"))
        self.assertContains(response, "Connected · 3")
        self.assertContains(response, "HTTPStatusError: 503")
        self.assertContains(response, reverse("source_new", args=["github"]))
        self.assertContains(response, "Needs STRAVA_CLIENT_ID")

    def test_connect_feed_imports_immediately(self):
        self.assertContains(self.client.get(reverse("source_new", args=["feed"])), "Feed URL")
        with mock.patch("tracker.sync.make_client", side_effect=feed_client):
            response = self.client.post(reverse("source_new", args=["feed"]), {"feed_url": "https://example.com/feed.xml"})
        self.assertRedirects(response, reverse("sources"))
        source = Source.objects.get(user=self.user, name="example.com")
        self.assertEqual(source.activities.get().title, "Hello")

    def test_connect_webhook(self):
        self.client.post(reverse("source_new", args=["webhook"]))
        self.assertTrue(Source.objects.filter(user=self.user, kind="webhook", name="Webhook").exists())

    def test_unknown_kind(self):
        self.assertEqual(self.client.get(reverse("source_new", args=["myspace"])).status_code, 404)

    def test_strava_goes_through_oauth(self):
        self.assertRedirects(self.client.get(reverse("source_new", args=["strava"])), reverse("strava_connect"), target_status_code=302)

    def test_edit_keeps_secret_when_left_empty(self):
        github = baker.make(Source, user=self.user, kind="github", config={"username": "a"}, secrets={"token": "keep"})
        response = self.client.get(reverse("source_edit", args=[github.pk]))
        self.assertContains(response, "Leave empty to keep the current one")
        self.assertNotContains(response, 'value="keep"')
        self.client.post(reverse("source_edit", args=[github.pk]), {"name": "Renamed", "username": "b", "token": "", "enabled": "on"})
        github.refresh_from_db()
        self.assertEqual((github.name, github.config["username"], github.secrets["token"]), ("Renamed", "b", "keep"))

    def test_edit_webhook_shows_url(self):
        response = self.client.get(reverse("source_edit", args=[self.hook.pk]))
        self.assertContains(response, f"/in/{self.hook.webhook_token}")
        self.client.post(reverse("source_edit", args=[self.hook.pk]), {"name": "Phone"})
        self.hook.refresh_from_db()
        self.assertEqual(self.hook.name, "Phone")
        self.assertFalse(self.hook.enabled)

    def test_sync_now(self):
        with mock.patch("tracker.sync.make_client", side_effect=feed_client):
            response = self.client.post(reverse("source_sync", args=[self.feed.pk]))
        self.assertRedirects(response, reverse("sources"))
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.last_error, "")

    def test_delete_removes_activities(self):
        self.client.post(reverse("source_delete", args=[self.feed.pk]))
        self.assertFalse(Activity.objects.filter(external_id="p1").exists())
        self.posts_goal.refresh_from_db()
        self.assertIsNone(self.posts_goal.source)

    def test_other_users_source(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("source_edit", args=[self.feed.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("source_sync", args=[self.feed.pk])).status_code, 404)


@override_settings(STRAVA_CLIENT_ID="123", STRAVA_CLIENT_SECRET="shh")
class StravaOAuthTest(TrackerViewTestCase):
    def test_sources_page_links_straight_to_oauth_without_boost(self):
        response = self.client.get(reverse("sources"))
        self.assertRegex(response.content.decode(), rf'href="{reverse("strava_connect")}"\s+hx-boost="false"')
        self.assertNotContains(response, "Needs STRAVA_CLIENT_ID")

    def test_connect_and_callback(self):
        response = self.client.get(reverse("strava_connect"))
        self.assertTrue(response.url.startswith("https://www.strava.com/oauth/authorize?client_id=123"))
        state = self.client.session["strava_state"]

        tokens = {"access_token": "a", "refresh_token": "r", "expires_at": 9999999999, "athlete": {"id": 5, "firstname": "Anže"}}
        with (
            mock.patch("tracker.views.request_token", return_value=tokens) as request_token,
            mock.patch("tracker.views.sync_source_task.delay") as delay,
        ):
            response = self.client.get(reverse("strava_callback"), {"state": state, "code": "abc"})
        self.assertRedirects(response, reverse("sources"))
        self.assertEqual(request_token.call_args.kwargs, {"code": "abc", "grant_type": "authorization_code"})
        source = Source.objects.get(user=self.user, kind="strava", config__athlete_id=5)
        self.assertEqual(source.name, "Strava · Anže")
        self.assertEqual(source.secrets["refresh_token"], "r")
        delay.assert_called_once_with(source.pk)

    def test_callback_rejects_bad_state(self):
        self.client.get(reverse("strava_connect"))
        response = self.client.get(reverse("strava_callback"), {"state": "forged", "code": "abc"}, follow=True)
        self.assertContains(response, "Strava connection expired")

    def test_callback_denied(self):
        self.client.get(reverse("strava_connect"))
        state = self.client.session["strava_state"]
        response = self.client.get(reverse("strava_callback"), {"state": state, "error": "access_denied"}, follow=True)
        self.assertContains(response, "access wasn")

    def test_callback_token_error(self):
        self.client.get(reverse("strava_connect"))
        state = self.client.session["strava_state"]
        with mock.patch("tracker.views.request_token", side_effect=SyncError("Strava token request failed (400)")):
            response = self.client.get(reverse("strava_callback"), {"state": state, "code": "abc"}, follow=True)
        self.assertContains(response, "Strava token request failed (400)")

    @override_settings(STRAVA_CLIENT_ID="")
    def test_not_configured(self):
        response = self.client.get(reverse("strava_connect"), follow=True)
        self.assertContains(response, "Set STRAVA_CLIENT_ID")


class WebhookTest(TrackerViewTestCase):
    def url(self) -> str:
        return reverse("webhook", args=[self.hook.webhook_token])

    def test_daily_total_replaces_earlier_post(self):
        self.client.logout()
        for steps in (5000, 9214):
            response = self.client.post(
                self.url(), {"type": "steps", "value": steps, "date": "2026-10-18"}, content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)
        activity = self.hook.activities.get()
        self.assertEqual((activity.type, activity.value, activity.external_id), ("steps", 9214, "steps:2026-10-18"))
        self.assertEqual(timezone.localtime(activity.occurred_at).date().isoformat(), "2026-10-18")

    def test_form_post_and_batch(self):
        response = self.client.post(self.url(), {"type": "Surf"})
        self.assertEqual(json.loads(response.content), {"ok": True, "created": 1, "received": 1})
        batch = [{"type": "steps", "value": 1, "date": f"2026-01-0{d}"} for d in range(1, 4)]
        response = self.client.post(self.url(), batch, content_type="application/json")
        self.assertEqual(json.loads(response.content)["created"], 3)
        self.assertEqual(self.hook.activities.filter(type="surf").count(), 1)
        self.hook.refresh_from_db()
        self.assertIsNotNone(self.hook.last_synced_at)

    def test_occurred_at_and_id(self):
        self.client.post(self.url(), {"type": "surf", "id": "s-1", "occurred_at": "2026-05-01T07:30:00"}, content_type="application/json")
        self.client.post(self.url(), {"type": "surf", "id": "s-1", "occurred_at": "2026-05-01T07:30:00"}, content_type="application/json")
        self.assertEqual(self.hook.activities.filter(external_id="s-1").count(), 1)

    def test_bad_requests(self):
        cases = [
            ("not json", "Invalid JSON"),
            (json.dumps({"value": "many"}), "value must be a number"),
            (json.dumps({"date": "yesterday"}), "date must be YYYY-MM-DD"),
            (json.dumps(["nope"]), "Each item must be an object"),
            (json.dumps([{}] * 1001), "At most 1000 items"),
        ]
        for body, error in cases:
            response = self.client.post(self.url(), body, content_type="application/json")
            self.assertEqual(response.status_code, 400, body[:20])
            self.assertIn(error, json.loads(response.content)["error"])

    def test_unknown_token_and_get(self):
        self.assertEqual(self.client.post(reverse("webhook", args=["nope"]), {}).status_code, 404)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_only_webhook_sources_accept_pushes(self):
        self.assertEqual(self.client.post(reverse("webhook", args=[self.feed.webhook_token]), {}).status_code, 404)
