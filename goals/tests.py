from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker

from goals.models import Board, Goal, Group, Result
from users.models import User


class ArchiveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(User)
        cls.board = baker.make(Board, user=cls.user, name="2021 Goals")
        cls.deleted = baker.make(Board, user=cls.user, name="Deleted board", date_deleted=timezone.now())
        group = baker.make(Group, board=cls.board, user=cls.user, name="Health")
        goal = baker.make(Goal, group=group, user=cls.user, name="Run 100 km")
        baker.make(Result, goal=goal, index=1, amount=12, expected_amount=10)
        baker.make(Result, goal=goal, index=2, amount=3, expected_amount=10)
        baker.make(Result, goal=goal, index=3, amount=4, expected_amount=None)

    def setUp(self):
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("archive"))
        self.assertRedirects(response, "/login?next=/archive/", fetch_redirect_response=False)

    def test_list(self):
        response = self.client.get(reverse("archive"))
        self.assertContains(response, "2021 Goals")
        self.assertContains(response, reverse("archive_board", args=[self.board.pk]))
        self.assertNotContains(response, "Deleted board")

    def test_board(self):
        response = self.client.get(reverse("archive_board", args=[self.board.pk]))
        self.assertContains(response, "Health")
        self.assertContains(response, "Run 100 km")
        self.assertContains(response, '<td class="met"', count=1)
        self.assertContains(response, '<td class="missed"', count=2)
        self.assertContains(response, '<td class="plain"', count=1)
        self.assertContains(response, "19")
        self.assertContains(response, "<small>/ 20</small>", html=True)

    def test_other_users_and_deleted_boards(self):
        self.assertEqual(self.client.get(reverse("archive_board", args=[self.deleted.pk])).status_code, 404)
        self.client.force_login(baker.make(User))
        self.assertEqual(self.client.get(reverse("archive_board", args=[self.board.pk])).status_code, 404)
