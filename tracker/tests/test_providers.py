import json
import time
import xmlrpc.client
from datetime import UTC, datetime
from typing import ClassVar
from unittest import mock

import httpx
from django.test import TestCase, override_settings
from model_bakery import baker

from tracker.models import Source
from tracker.providers import get_provider
from tracker.providers.feeds import GoodreadsForm, parse_date
from tracker.providers.mastodon import MastodonForm
from tracker.providers.pypi import PyPIForm
from tracker.providers.strava import activity_type_for
from users.models import User

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Blog</title>
<item><title>The 15-Year-Old iptables Rule</title><link>http://blog.pecar.me/iptables/</link>
<pubDate>Mon, 08 Jun 2026 01:15:00 +0100</pubDate><guid>http://blog.pecar.me/iptables/</guid></item>
<item><title>No date</title><link>http://blog.pecar.me/draft/</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry><id>tag:example.com,2026:1</id><title>Hello</title><link href="https://example.com/hello"/>
<updated>2026-02-03T10:00:00Z</updated></entry>
</feed>"""

GOODREADS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Dune</title><link>https://www.goodreads.com/review/show/1</link><book_id>234225</book_id>
<user_read_at>Sat, 14 Mar 2026 00:00:00 -0700</user_read_at><user_date_added>Mon, 01 Jan 2024 00:00:00 -0700</user_date_added>
<pubDate>Mon, 01 Jan 2024 00:00:00 -0700</pubDate></item>
<item><title>No read date</title><link>https://www.goodreads.com/review/show/2</link><book_id>99</book_id>
<user_read_at></user_read_at><user_date_added>Tue, 02 Jun 2026 00:00:00 -0700</user_date_added></item>
</channel></rss>"""


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class ProviderTestCase(TestCase):
    user: ClassVar[User]

    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(User)

    def make_source(self, kind: str, config: dict | None = None, secrets: dict | None = None) -> Source:
        return baker.make(Source, user=self.user, kind=kind, config=config or {}, secrets=secrets or {})


class FeedProviderTest(ProviderTestCase):
    def test_rss(self):
        source = self.make_source("feed", {"feed_url": "https://blog.pecar.me/feed.xml"})
        client = client_for(lambda request: httpx.Response(200, content=RSS))
        [post] = list(source.provider.fetch(source, client, since=None))
        self.assertEqual(post.type, "post")
        self.assertEqual(post.external_id, "http://blog.pecar.me/iptables/")
        self.assertEqual(post.occurred_at, datetime(2026, 6, 8, 0, 15, tzinfo=UTC))
        self.assertEqual(post.title, "The 15-Year-Old iptables Rule")

    def test_atom(self):
        source = self.make_source("feed", {"feed_url": "https://example.com/atom.xml"})
        [post] = list(source.provider.fetch(source, client_for(lambda r: httpx.Response(200, content=ATOM)), since=None))
        self.assertEqual(post.external_id, "tag:example.com,2026:1")
        self.assertEqual(post.url, "https://example.com/hello")
        self.assertEqual(post.occurred_at, datetime(2026, 2, 3, 10, tzinfo=UTC))

    def test_invalid_feed(self):
        source = self.make_source("feed", {"feed_url": "https://example.com/"})
        with self.assertRaisesMessage(Exception, "Not a valid feed"):
            list(source.provider.fetch(source, client_for(lambda r: httpx.Response(200, content=b"<html")), since=None))

    def test_default_name(self):
        self.assertEqual(get_provider("feed").default_name({"feed_url": "https://blog.pecar.me/feed.xml"}), "blog.pecar.me")

    def test_parse_date(self):
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date("not a date"))
        self.assertEqual(parse_date("2026-01-01T10:00:00"), datetime(2026, 1, 1, 10, tzinfo=UTC))


class GoodreadsProviderTest(ProviderTestCase):
    def test_read_shelf(self):
        source = self.make_source("goodreads", {"user_id": "42"})
        pages = []

        def handler(request: httpx.Request) -> httpx.Response:
            pages.append(request.url.params["page"])
            self.assertEqual(request.url.path, "/review/list_rss/42")
            self.assertEqual(request.url.params["shelf"], "read")
            return httpx.Response(200, content=GOODREADS if request.url.params["page"] == "1" else b"<rss><channel/></rss>")

        dune, undated = list(source.provider.fetch(source, client_for(handler), since=None))
        self.assertEqual(pages, ["1", "2"])
        self.assertEqual(dune.external_id, "book:234225")
        self.assertEqual(dune.occurred_at.date().isoformat(), "2026-03-14")
        # Falls back to when it was added to the shelf
        self.assertEqual(undated.occurred_at.date().isoformat(), "2026-06-02")

    def test_form_accepts_profile_url(self):
        form = GoodreadsForm({"user_id": "https://www.goodreads.com/user/show/12345-anze"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["user_id"], "12345")
        self.assertFalse(GoodreadsForm({"user_id": "anze"}).is_valid())


class GitHubProviderTest(ProviderTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/users/anze3db/repos":
            return httpx.Response(
                200,
                json=[
                    {"name": "goals", "full_name": "anze3db/goals", "fork": False, "pushed_at": "2026-10-01T00:00:00Z"},
                    {"name": "old", "full_name": "anze3db/old", "fork": False, "pushed_at": "2020-01-01T00:00:00Z"},
                    {"name": "fork", "full_name": "anze3db/fork", "fork": True, "pushed_at": "2026-10-01T00:00:00Z"},
                ],
            )
        if path == "/repos/anze3db/goals/releases":
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "draft": False, "published_at": "2026-09-01T12:00:00Z", "tag_name": "v1.0", "html_url": "https://gh/1"},
                    {"id": 2, "draft": True, "published_at": None, "tag_name": "v1.1", "html_url": "https://gh/2"},
                ],
            )
        if path == "/repos/anze3db/old/releases":
            return httpx.Response(
                200, json=[{"id": 3, "draft": False, "published_at": "2020-01-01T00:00:00Z", "tag_name": "v0", "html_url": ""}]
            )
        if path == "/graphql":
            self.assertEqual(request.headers["Authorization"], "Bearer secret")
            self.assertEqual(json.loads(request.content)["variables"]["login"], "anze3db")
            days = [{"date": "2026-10-01", "contributionCount": 4}, {"date": "2026-10-02", "contributionCount": 0}]
            return httpx.Response(
                200, json={"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [{"contributionDays": days}]}}}}}
            )
        return httpx.Response(404)

    def test_releases_and_contributions(self):
        source = self.make_source("github", {"username": "anze3db"}, {"token": "secret"})
        fetched = list(source.provider.fetch(source, client_for(self.handler), since=None))
        self.assertEqual(
            [(f.type, f.external_id, f.value) for f in fetched],
            [("release", "release:1", 1), ("release", "release:3", 1), ("contribution", "contribution:2026-10-01", 4)],
        )
        self.assertEqual(fetched[0].title, "goals v1.0")

    def test_incremental_sync_skips_untouched_repos_and_contributions_without_token(self):
        source = self.make_source("github", {"username": "anze3db"})
        fetched = list(source.provider.fetch(source, client_for(self.handler), since=datetime(2026, 6, 1, tzinfo=UTC)))
        self.assertEqual([f.external_id for f in fetched], ["release:1"])

    def test_graphql_errors(self):
        source = self.make_source("github", {"username": "anze3db"}, {"token": "secret"})

        def handler(request):
            if request.url.path == "/graphql":
                return httpx.Response(200, json={"errors": [{"message": "Bad credentials"}]})
            return httpx.Response(200, json=[])

        with self.assertRaisesMessage(Exception, "Bad credentials"):
            list(source.provider.fetch(source, client_for(handler), since=None))


class PyPIProviderTest(ProviderTestCase):
    def test_user_packages_and_extra_packages(self):
        source = self.make_source("pypi", {"username": "anze3db", "packages": ["django-tui", "missing"]})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                self.assertIn(b"user_packages", request.content)
                return httpx.Response(
                    200, content=xmlrpc.client.dumps(([["Owner", "potatoq"], ["Owner", "django-tui"]],), methodresponse=True)
                )
            if request.url.path == "/pypi/missing/json":
                return httpx.Response(404)
            name = request.url.path.split("/")[2]
            return httpx.Response(
                200,
                json={
                    "info": {"name": name},
                    "releases": {
                        "1.0": [
                            {"upload_time_iso_8601": "2026-05-02T10:00:00Z"},
                            {"upload_time_iso_8601": "2026-05-01T10:00:00Z"},
                        ],
                        "0.9": [],
                    },
                },
            )

        fetched = list(source.provider.fetch(source, client_for(handler), since=None))
        self.assertEqual([f.external_id for f in fetched], ["django-tui==1.0", "potatoq==1.0"])
        self.assertEqual(fetched[0].occurred_at, datetime(2026, 5, 1, 10, tzinfo=UTC))
        self.assertEqual(fetched[1].url, "https://pypi.org/project/potatoq/1.0/")

    def test_form_needs_username_or_packages(self):
        self.assertFalse(PyPIForm({}).is_valid())
        form = PyPIForm({"packages": "a\nb  c"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["packages"], ["a", "b", "c"])


@override_settings(STRAVA_CLIENT_ID="123", STRAVA_CLIENT_SECRET="shh")
class StravaProviderTest(ProviderTestCase):
    def test_refreshes_token_and_fetches(self):
        source = self.make_source("strava", {"athlete_id": 1}, {"access_token": "old", "refresh_token": "r", "expires_at": 0})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth/token":
                self.assertIn(b"grant_type=refresh_token", request.content)
                return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "expires_at": time.time() + 3600})
            self.assertEqual(request.headers["Authorization"], "Bearer new")
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 7,
                        "sport_type": "TrailRun",
                        "type": "Run",
                        "start_date": "2026-04-01T06:00:00Z",
                        "distance": 10450.0,
                        "name": "Hills",
                    },
                    {
                        "id": 8,
                        "sport_type": "Surfing",
                        "type": "Surfing",
                        "start_date": "2026-04-02T06:00:00Z",
                        "distance": 0,
                        "name": "Dawn patrol",
                    },
                ],
            )

        run, surf = list(source.provider.fetch(source, client_for(handler), since=None))
        self.assertEqual((run.type, run.value, run.external_id), ("run", 10.45, "7"))
        self.assertEqual(run.url, "https://www.strava.com/activities/7")
        self.assertEqual(surf.type, "surf")
        source.refresh_from_db()
        self.assertEqual(source.secrets["access_token"], "new")
        self.assertEqual(source.secrets["refresh_token"], "r2")

    def test_failed_refresh(self):
        source = self.make_source("strava", {}, {"access_token": "old", "refresh_token": "r", "expires_at": 0})
        with self.assertRaisesMessage(Exception, "Strava token request failed (401)"):
            list(source.provider.fetch(source, client_for(lambda r: httpx.Response(401, text="nope")), since=None))

    def test_activity_type_for(self):
        self.assertEqual(activity_type_for("VirtualRide"), "ride")
        self.assertEqual(activity_type_for("WeightTraining"), "strength")
        self.assertEqual(activity_type_for("RockClimbing"), "rock_climbing")


class MastodonProviderTest(ProviderTestCase):
    def test_followers_posts_and_engagement(self):
        source = self.make_source("mastodon", {"handle": "@anze@mastodon.social"})

        def status(status_id, created_at, **kwargs):
            return {
                "id": status_id,
                "created_at": created_at,
                "content": "<p>Hello <b>world</b></p>",
                "url": f"https://mastodon.social/@anze/{status_id}",
                "favourites_count": 3,
                "reblogs_count": 2,
                "replies_count": 1,
            } | kwargs

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/accounts/lookup":
                self.assertEqual(request.url.params["acct"], "anze")
                return httpx.Response(200, json={"id": "9", "followers_count": 1500})
            if "max_id" not in request.url.params:
                return httpx.Response(
                    200,
                    json=[status("3", "2020-01-01T00:00:00Z", pinned=True), status("2", "2026-05-01T10:00:00Z")],
                )
            self.assertEqual(request.url.params["max_id"], "2")
            return httpx.Response(200, json=[status("1", "2020-01-01T00:00:00Z")])

        with mock.patch("tracker.providers.mastodon.fetch_cutoff", return_value=datetime(2026, 1, 1, tzinfo=UTC)):
            fetched = list(source.provider.fetch(source, client_for(handler), since=None))

        self.assertEqual([(f.type, f.value) for f in fetched], [("followers", 1500), ("post", 1), ("engagement", 6)])
        self.assertEqual(fetched[1].title, "Hello world")
        self.assertEqual(fetched[2].external_id, "engagement:2")

    def test_form(self):
        for value in ("@Anze@Mastodon.Social", "anze@mastodon.social", "https://mastodon.social/@anze"):
            form = MastodonForm({"handle": value})
            self.assertTrue(form.is_valid(), value)
            self.assertEqual(form.cleaned_data["handle"].lower(), "@anze@mastodon.social")
        self.assertFalse(MastodonForm({"handle": "anze"}).is_valid())
